#!/usr/bin/env python3
"""vRemoter for Linux: button remapping and voice hooks for the Chromecast Voice Remote.

The remote's microphone is handled by ATVVoice (https://github.com/b0o/ATVVoice), which exposes it as a PipeWire source
and publishes its state on the session D-Bus. This daemon covers the rest of what the macOS app does:

1. Grabs the remote's HID input device so its TV-oriented keys (Power -> KEY_SCREENLOCK, YouTube -> KEY_CAMERA_ACCESS_*)
   no longer reach the desktop, and re-emits the configured key, key combo, command or ATVVoice action instead.
2. Watches ATVVoice's MicStateChanged signal and runs user commands when the remote microphone starts or stops streaming.

Button identities follow the remote's HID report descriptor (Consumer page usages). The descriptor is an array of 17
usages; the remote sends the 1-based index of the pressed one, which the macOS app uses as its button id. Only 15 of
them are physical keys (the 15th, Voice, arrives over ATVV instead), and the macOS RemoteProfiles.chromecastButtons
lists just those. See BUTTONS for the other three.
"""

import argparse
import os
import signal
import subprocess
import sys
import tomllib

import dbus
import dbus.mainloop.glib
import evdev
import gi
from evdev import ecodes
from gi.repository import GLib

VENDOR_ID = 0x18D1
PRODUCT_ID = 0x9450

# HID Consumer usage (as reported in EV_MSC/MSC_SCAN, page 0x0C) -> button name.
# Report index in parentheses matches the button id used by the macOS app.
# play_pause (02), search (09) and usage_79 (10) are declared in the descriptor but no key on this remote sends them
# (never seen in testing, and absent from the macOS button list). Most likely the descriptor is shared with other Google
# TV remotes that do have those keys. They stay here so a stray report is still grabbed and can be mapped from the config
# file; the GUI's mapping table hides them.
BUTTONS = {
	0x000C019E: "power",  # (01) AL Terminal Lock; kernel maps to KEY_SCREENLOCK
	0x000C00CD: "play_pause",  # (02) descriptor only; no such key on this remote
	0x000C0042: "up",  # (03)
	0x000C0043: "down",  # (04)
	0x000C0044: "left",  # (05)
	0x000C0045: "right",  # (06)
	0x000C0041: "select",  # (07)
	0x000C00E2: "mute",  # (08)
	0x000C0221: "search",  # (09) AC Search, descriptor only; the Voice key sends START_SEARCH over ATVV, not this usage
	0x000C0223: "home",  # (0A)
	0x000C0224: "back",  # (0B)
	0x000C00E9: "volume_up",  # (0C)
	0x000C00EA: "volume_down",  # (0D)
	0x000C0077: "youtube",  # (0E) kernel maps to KEY_CAMERA_ACCESS_DISABLE
	0x000C0078: "netflix",  # (0F) kernel maps to KEY_CAMERA_ACCESS_TOGGLE
	0x000C0079: "usage_79",  # (10) descriptor only; probably another app key on other models; kernel maps to KEY_KBDILLUMUP
	0x000C0089: "input",  # (11) kernel maps to KEY_TV
}

# Defaults mirror the macOS app: navigation keys stay useful, TV-only keys are disabled.
DEFAULT_BUTTONS = {
	"power": "none",
	"play_pause": "KEY_PLAYPAUSE",
	"up": "KEY_UP",
	"down": "KEY_DOWN",
	"left": "KEY_LEFT",
	"right": "KEY_RIGHT",
	"select": "KEY_ENTER",
	"mute": "KEY_MUTE",
	"search": "none",
	"home": "KEY_LEFTMETA+KEY_D",
	"back": "KEY_ESC",
	"volume_up": "KEY_VOLUMEUP",
	"volume_down": "KEY_VOLUMEDOWN",
	"youtube": "none",
	"netflix": "none",
	"usage_79": "none",
	"input": "none",
}

DEFAULT_VOICE = {
	"atvvoice_name": "chromecast-remote",
	"on_start": "",
	"on_stop": "",
}

ATVV_INTERFACE = "org.atvvoice.Daemon"
ATVV_PATH = "/org/atvvoice/Daemon"
# ATVVoice D-Bus methods per action: (on press, on release).
ATVV_ACTIONS = {"atvv:open": ("MicOpen", None), "atvv:close": ("MicClose", None), "atvv:toggle": ("MicToggle", None), "atvv:hold": ("MicOpen", "MicClose")}

DEFAULT_CONFIG_PATH = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "vremoter", "config.toml")


def add_signal_handler(signum, handler):
	"""GLibUnix.signal_add on newer PyGObject (where GLib.unix_signal_add is deprecated); GLib.unix_signal_add on older (Ubuntu 24.04)."""
	try:
		gi.require_version("GLibUnix", "2.0")
		from gi.repository import GLibUnix
		if hasattr(GLibUnix, "signal_add"):
			return GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signum, handler)
	except (ImportError, ValueError):
		pass
	return GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, handler)


def log(message):
	print(message, flush=True)


class Target:
	"""A button's configured actions: a key combo, shell commands and/or ATVVoice D-Bus methods.

	`spec` is one action string or a list of them, e.g. ["atvv:hold", "KEY_RIGHTALT+KEY_0"]. ATVVoice actions run before
	keys are pressed and after they are released, so a voice input method triggered by the keys sees the mic open.
	"""

	def __init__(self, spec):
		parts = [spec] if isinstance(spec, str) else list(spec)
		self.spec = " & ".join(p.strip() for p in parts)
		self.keys = []
		self.commands = []
		self.atvv_press = []
		self.atvv_release = []
		for part in (p.strip() for p in parts):
			if part in ("", "none"):
				continue
			if part.startswith("cmd:"):
				self.commands.append(part[4:].strip())
			elif part in ATVV_ACTIONS:
				on_press, on_release = ATVV_ACTIONS[part]
				self.atvv_press.append(on_press)
				if on_release:
					self.atvv_release.append(on_release)
			else:
				if self.keys:
					raise ValueError(f"only one key combo per button: {self.spec!r}")
				for name in part.split("+"):
					code = ecodes.ecodes.get(name.strip())
					if code is None or not name.strip().startswith(("KEY_", "BTN_")):
						raise ValueError(f"unknown key {name.strip()!r} in {self.spec!r}")
					self.keys.append(code)


def load_config(path):
	buttons = dict(DEFAULT_BUTTONS)
	voice = dict(DEFAULT_VOICE)
	if os.path.exists(path):
		with open(path, "rb") as f:
			data = tomllib.load(f)
		unknown = set(data.get("buttons", {})) - set(DEFAULT_BUTTONS)
		if unknown:
			raise ValueError(f"unknown button names in {path}: {', '.join(sorted(unknown))}")
		buttons.update(data.get("buttons", {}))
		voice.update(data.get("voice", {}))
		log(f"[config] loaded {path}")
	else:
		log(f"[config] {path} not found; using defaults")
	return {name: Target(spec) for name, spec in buttons.items()}, voice


def run_command(command, label):
	if not command:
		return
	log(f"[cmd] {label}: {command}")
	subprocess.Popen(command, shell=True, start_new_session=True, stdin=subprocess.DEVNULL)


class Remapper:
	"""Grabs the remote's evdev node and re-emits mapped actions through a uinput device."""

	def __init__(self, targets, atvv):
		self.targets = targets
		self.atvv = atvv
		# Advertise a full standard keyboard, not just the mapped keys: apps that read input devices themselves (Vokie's
		# input helper) skip devices that do not look like a keyboard, and then never see its hotkeys from the remote.
		keys = {code for t in targets.values() for code in t.keys} | {code for code in range(ecodes.KEY_ESC, ecodes.KEY_MICMUTE + 1) if code in ecodes.KEY}
		self.uinput = evdev.UInput({ecodes.EV_KEY: sorted(keys)}, name="vRemoter Chromecast Remote", vendor=VENDOR_ID, product=PRODUCT_ID)
		self.device = None
		self.watch_id = None
		self.last_scan = None
		self.held = {}  # evdev keycode from the remote -> Target currently pressed

	def find_device(self):
		for path in evdev.list_devices():
			try:
				dev = evdev.InputDevice(path)
			except OSError:
				continue
			# Skip our own uinput device, which carries the same vendor/product ids.
			own = dev.path == self.uinput.device.path
			if not own and dev.info.vendor == VENDOR_ID and dev.info.product == PRODUCT_ID and ecodes.EV_KEY in dev.capabilities():
				return dev
			dev.close()
		return None

	def poll_device(self):
		if self.device is None:
			dev = self.find_device()
			if dev is not None:
				try:
					dev.grab()
				except OSError as e:
					log(f"[hid] cannot grab {dev.path}: {e}")
					dev.close()
					return True
				self.device = dev
				self.watch_id = GLib.io_add_watch(dev.fd, GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP, self.on_readable)
				log(f"[hid] grabbed {dev.path} ({dev.name})")
		return True  # keep the GLib timeout alive

	def drop_device(self):
		self.release_all()
		if self.watch_id is not None:
			GLib.source_remove(self.watch_id)
			self.watch_id = None
		if self.device is not None:
			log(f"[hid] lost {self.device.path}")
			try:
				self.device.close()
			except OSError:
				pass
			self.device = None

	def on_readable(self, fd, condition):
		try:
			for event in self.device.read():
				self.handle(event)
		except (OSError, BlockingIOError) as e:
			if isinstance(e, BlockingIOError):
				return True
			self.drop_device()
			return False
		if condition & (GLib.IO_ERR | GLib.IO_HUP):
			self.drop_device()
			return False
		return True

	def handle(self, event):
		if event.type == ecodes.EV_MSC and event.code == ecodes.MSC_SCAN:
			self.last_scan = event.value
		elif event.type == ecodes.EV_KEY:
			if event.value == 1:
				name = BUTTONS.get(self.last_scan, f"unknown_{self.last_scan or 0:08x}")
				target = self.targets.get(name)
				log(f"[key] {name} DOWN -> {target.spec if target else 'unmapped'}")
				if target is not None:
					self.held[event.code] = target
					self.press(target, name)
			elif event.value == 2:
				target = self.held.get(event.code)
				if target is not None and len(target.keys) == 1:
					self.emit(target.keys[0], 2)
			elif event.value == 0:
				target = self.held.pop(event.code, None)
				if target is not None:
					self.release(target)
			self.last_scan = None

	def emit(self, code, value):
		self.uinput.write(ecodes.EV_KEY, code, value)
		self.uinput.syn()

	def press(self, target, name):
		for method in target.atvv_press:
			self.atvv.call(method)
		for code in target.keys:
			self.emit(code, 1)
		for command in target.commands:
			run_command(command, name)

	def release(self, target):
		for code in reversed(target.keys):
			self.emit(code, 0)
		for method in target.atvv_release:
			self.atvv.call(method)

	def release_all(self):
		for target in self.held.values():
			self.release(target)
		self.held.clear()


class AtvVoice:
	"""Talks to the ATVVoice daemon over the session bus and runs voice hooks on its state changes."""

	def __init__(self, bus, voice):
		self.bus = bus
		self.bus_name = f"org.atvvoice.{voice['atvvoice_name']}"
		self.on_start = voice["on_start"]
		self.on_stop = voice["on_stop"]
		self.streaming = False
		bus.add_signal_receiver(self.on_state, signal_name="MicStateChanged", dbus_interface=ATVV_INTERFACE, path=ATVV_PATH)

	def on_state(self, state):
		state = str(state)
		log(f"[voice] ATVVoice state -> {state}")
		if state == "streaming" and not self.streaming:
			self.streaming = True
			run_command(self.on_start, "voice on_start")
		elif state in ("connected", "disconnected") and self.streaming:
			# "opening" is not a stop: a voice-key tap hands its hold-to-talk stream over to a persistent MIC_OPEN stream.
			self.streaming = False
			run_command(self.on_stop, "voice on_stop")

	def call(self, method):
		try:
			proxy = self.bus.get_object(self.bus_name, ATVV_PATH)
			proxy.get_dbus_method(method, ATVV_INTERFACE)(reply_handler=lambda *a: None, error_handler=lambda e: log(f"[voice] {method} failed: {e}"))
			log(f"[voice] {method} sent to {self.bus_name}")
		except dbus.DBusException as e:
			log(f"[voice] cannot reach {self.bus_name}: {e}")


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH, help=f"config file (default: {DEFAULT_CONFIG_PATH})")
	parser.add_argument("--check", action="store_true", help="validate the config and exit")
	args = parser.parse_args()

	try:
		targets, voice = load_config(args.config)
	except (ValueError, tomllib.TOMLDecodeError) as e:
		log(f"[config] error: {e}")
		return 2
	if args.check:
		for name, target in targets.items():
			log(f"  {name:12} {target.spec or 'none'}")
		return 0

	dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
	atvv = AtvVoice(dbus.SessionBus(), voice)
	remapper = Remapper(targets, atvv)
	remapper.poll_device()
	GLib.timeout_add_seconds(2, remapper.poll_device)

	loop = GLib.MainLoop()
	for signum in (signal.SIGTERM, signal.SIGINT):
		add_signal_handler(signum, loop.quit)
	log("[main] running")
	try:
		loop.run()
	finally:
		remapper.drop_device()
		remapper.uinput.close()
	return 0


if __name__ == "__main__":
	sys.exit(main())
