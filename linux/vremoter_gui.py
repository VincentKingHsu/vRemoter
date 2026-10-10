#!/usr/bin/env python3
"""vRemoter for Linux - console for the Chromecast Voice Remote, styled after the macOS app's frozen "Studio Mixer" design.

A front end over the two background services:

1. vremoter-linux (vremoter_linux.py) grabs the remote's keys; this window follows its journal to see presses, and edits its
   config file for mappings.
2. atvvoice exposes the remote microphone as a PipeWire source; this window follows its D-Bus state and journal for voice-key
   gestures, records from the source and can change its gain and filters.

Pages: 音频 (mic strip, level history, audio processing, status checks, recordings), 按键映射 (device, remote picture, mapping
list), 测试 (key and voice tests on the remote picture) and 日志 (service logs).
"""

import array
import collections
import math
import os
import re
import subprocess
import sys
import time
import wave

from PyQt6 import QtDBus
from PyQt6.QtCore import QProcess, QRectF, QSize, QStringListModel, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox, QCompleter, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
								QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout,
								QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vremoter_linux as daemon  # noqa: E402

SOURCE_NAME = "atvvoice-chromecast-remote"
SAMPLE_RATE = 16000
ATVV_NAME = "chromecast-remote"
ATVV_SERVICE = f"org.atvvoice.{ATVV_NAME}"
ATVV_OVERRIDE = os.path.expanduser("~/.config/systemd/user/atvvoice.service.d/override.conf")
RECORDINGS_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "vremoter", "recordings")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
HERE = os.path.dirname(os.path.abspath(__file__))

# Colours of the macOS console (Sources/vRemote/DebugWindowController.swift, ConsoleTheme).
PANEL = "#0E0F11"
SURFACE = "#15171A"
SURFACE2 = "#1A1D20"
LINE = "#383B40"
LINE_SOFT = "#26292E"
TEXT = "#EDF0F2"
SECONDARY = "#8C919C"
TERTIARY = "#636973"
GREEN = "#4FD187"
AMBER = "#F59C30"
AMBER_DEEP = "#292117"
RED = "#F05457"
RED_DEEP = "#401417"
BLACK = "#060708"

STYLE = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QWidget#root, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {PANEL}; }}
QFrame#header {{ background: #111316; border: 1px solid {LINE_SOFT}; border-radius: 24px; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 18px; }}
QFrame#cardAmber {{ background: {AMBER_DEEP}; border: 1px solid {LINE_SOFT}; border-top: 3px solid {AMBER}; border-radius: 18px; }}
QFrame#inset {{ background: {SURFACE2}; border: 1px solid {LINE_SOFT}; border-radius: 12px; }}
QFrame#device {{ background: {SURFACE2}; border: 1px solid {LINE_SOFT}; border-radius: 13px; }}
QFrame#deviceActive {{ background: #13201A; border: 1px solid #2D6B48; border-radius: 13px; }}
QFrame#row {{ background: {SURFACE2}; border: none; border-radius: 10px; }}
QFrame#row[selected="true"] {{ background: #232017; border: 1px solid #5C4320; }}
QFrame#vline {{ background: {LINE_SOFT}; max-width: 1px; min-width: 1px; }}
QFrame#segment {{ background: {BLACK}; border-radius: 12px; }}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 24px; font-weight: 700; }}
QLabel#title {{ font-size: 19px; font-weight: 700; }}
QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#subtitle, QLabel#secondary {{ color: {SECONDARY}; }}
QLabel#caption {{ color: {TERTIARY}; font-size: 12px; }}
QLabel#mono {{ font-family: monospace; color: {SECONDARY}; }}
QLabel#good {{ color: {GREEN}; font-weight: 600; }}
QLabel#warn {{ color: {AMBER}; font-weight: 600; }}
QLabel#bad {{ color: {RED}; font-weight: 600; }}
QPushButton {{ background: {SURFACE2}; border: 1px solid {LINE}; border-radius: 9px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: #50555d; }}
QPushButton:pressed {{ background: #101214; }}
QPushButton:disabled {{ color: {TERTIARY}; border-color: {LINE_SOFT}; }}
QPushButton#primary {{ background: {GREEN}; color: #06130B; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #63dc98; }}
QPushButton#link {{ background: transparent; border: none; color: {GREEN}; font-weight: 700; padding: 4px 6px; }}
QPushButton#seg {{ background: transparent; border: none; color: {SECONDARY}; font-weight: 600; padding: 8px 18px; border-radius: 9px; }}
QPushButton#seg:checked {{ background: #23262A; color: {TEXT}; }}
QPushButton#target {{ background: #22252A; border: none; border-radius: 8px; padding: 6px 12px; text-align: left; }}
QPushButton#target:hover {{ background: #2A2E33; }}
QPushButton#target:disabled {{ background: transparent; color: {SECONDARY}; }}
QPushButton#record {{ background: {BLACK}; border: 1.5px solid {LINE}; border-radius: 12px; padding: 10px 18px; font-weight: 700; }}
QPushButton#record:checked {{ background: {RED_DEEP}; border-color: {RED}; color: #ffd9da; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {LINE}; background: {BLACK}; }}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; image: none; }}
QCheckBox:disabled {{ color: {TERTIARY}; }}
QSpinBox, QLineEdit {{ background: {BLACK}; border: 1px solid {LINE}; border-radius: 8px; padding: 4px 8px; selection-background-color: #2D6B48; }}
QSpinBox:disabled {{ color: {TERTIARY}; border-color: {LINE_SOFT}; }}
QListWidget {{ background: #0B0C0E; border: 1px solid {LINE_SOFT}; border-radius: 12px; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 7px; }}
QListWidget::item:selected {{ background: #23262A; color: {TEXT}; }}
QPlainTextEdit {{ background: #0B0C0E; border: 1px solid {LINE_SOFT}; border-radius: 12px; padding: 6px; font-family: monospace; font-size: 12px; }}
QMenu {{ background: {SURFACE2}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2A2E33; }}
QMenu::item:disabled {{ color: {TERTIARY}; }}
QMenu::separator {{ height: 1px; background: {LINE_SOFT}; margin: 5px 8px; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {LINE}; padding: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #33373D; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QDialog, QMessageBox, QInputDialog {{ background: {SURFACE}; }}
"""

# Button names (as in vremoter_linux.BUTTONS) -> label.
BUTTON_LABELS = {
	"power": "电源",
	"input": "信源",
	"up": "方向上",
	"left": "方向左",
	"select": "确认",
	"right": "方向右",
	"down": "方向下",
	"back": "返回",
	"home": "主页",
	"voice": "语音",
	"youtube": "YouTube",
	"netflix": "Netflix",
	"mute": "静音",
	"volume_up": "音量＋",
	"volume_down": "音量－",
	"play_pause": "播放/暂停",
	"search": "搜索",
	"usage_79": "未知 0x79",
}
# The 15 physical keys, in the order the mapping list shows them (top of the remote first). The HID descriptor also declares
# play_pause, search and usage_79, which no key on this remote sends; the editor hides them but keeps their configured values.
PHYSICAL_BUTTONS = ["up", "down", "left", "right", "select", "back", "voice", "home", "mute", "youtube", "netflix", "power", "input", "volume_up", "volume_down"]
# Text glyphs for keys whose picture crop would be ambiguous (the D-pad ring, the volume rocker on the side).
BUTTON_GLYPHS = {"up": "↑", "down": "↓", "left": "←", "right": "→", "select": "◉", "volume_up": "＋", "volume_down": "－"}

# Hotspots on Resources/RemoteImages/chromecast-voice-remote.png (388 x 1080): centre x, centre y, radius, in image pixels.
REMOTE_HOTSPOTS = {
	"up": (194, 62, 34),
	"down": (194, 268, 34),
	"left": (92, 165, 34),
	"right": (296, 165, 34),
	"select": (194, 165, 50),
	"back": (115, 378, 50),
	"voice": (270, 378, 50),
	"home": (115, 510, 50),
	"mute": (270, 510, 50),
	"youtube": (115, 640, 50),
	"netflix": (270, 640, 50),
	"power": (113, 773, 30),
	"input": (271, 773, 30),
	"volume_up": (362, 228, 24),
	"volume_down": (362, 298, 24),
}

# Mapping menu: (group, [(action, label), ...]). The label is what the editor shows for that action.
MAPPING_GROUPS = [
	("导航", [
		("KEY_UP", "方向上"),
		("KEY_DOWN", "方向下"),
		("KEY_LEFT", "方向左"),
		("KEY_RIGHT", "方向右"),
		("KEY_ENTER", "回车"),
		("KEY_ESC", "Esc"),
		("KEY_SPACE", "空格"),
		("KEY_TAB", "Tab"),
		("KEY_LEFTSHIFT+KEY_TAB", "Shift+Tab"),
		("KEY_BACKSPACE", "退格"),
		("KEY_DELETE", "Delete"),
		("KEY_HOME", "Home"),
		("KEY_END", "End"),
		("KEY_PAGEUP", "上翻页"),
		("KEY_PAGEDOWN", "下翻页"),
	]),
	("媒体", [
		("KEY_PLAYPAUSE", "播放/暂停"),
		("KEY_STOPCD", "停止"),
		("KEY_NEXTSONG", "下一曲"),
		("KEY_PREVIOUSSONG", "上一曲"),
		("KEY_FASTFORWARD", "快进"),
		("KEY_REWIND", "快退"),
		("KEY_MUTE", "系统静音"),
		("KEY_VOLUMEUP", "系统音量＋"),
		("KEY_VOLUMEDOWN", "系统音量－"),
		("KEY_MICMUTE", "麦克风静音"),
	]),
	("浏览器", [
		("KEY_BACK", "后退"),
		("KEY_FORWARD", "前进"),
		("KEY_LEFTALT+KEY_LEFT", "Alt+← 后退"),
		("KEY_LEFTALT+KEY_RIGHT", "Alt+→ 前进"),
		("KEY_REFRESH", "刷新"),
		("KEY_F5", "F5 刷新"),
		("KEY_F11", "F11 全屏"),
		("KEY_HOMEPAGE", "浏览器主页"),
		("KEY_LEFTCTRL+KEY_T", "新标签页"),
		("KEY_LEFTCTRL+KEY_W", "关闭标签页"),
		("KEY_LEFTCTRL+KEY_TAB", "下一个标签页"),
		("KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_TAB", "上一个标签页"),
		("KEY_LEFTCTRL+KEY_EQUAL", "放大"),
		("KEY_LEFTCTRL+KEY_MINUS", "缩小"),
		("KEY_LEFTCTRL+KEY_0", "原始大小"),
	]),
	("桌面 / 系统", [
		("KEY_LEFTMETA", "Meta（开始菜单）"),
		("KEY_LEFTMETA+KEY_D", "显示桌面"),
		("KEY_LEFTALT+KEY_TAB", "切换窗口"),
		("KEY_LEFTALT+KEY_F4", "关闭窗口"),
		("KEY_LEFTMETA+KEY_UP", "最大化窗口"),
		("KEY_LEFTCTRL+KEY_LEFTMETA+KEY_LEFT", "上一个虚拟桌面"),
		("KEY_LEFTCTRL+KEY_LEFTMETA+KEY_RIGHT", "下一个虚拟桌面"),
		("KEY_LEFTMETA+KEY_L", "锁屏（Meta+L）"),
		("KEY_SCREENLOCK", "锁屏键"),
		("KEY_SYSRQ", "截图"),
		("KEY_BRIGHTNESSUP", "亮度＋"),
		("KEY_BRIGHTNESSDOWN", "亮度－"),
		("KEY_SLEEP", "睡眠"),
		("KEY_POWER", "电源键（关机菜单）"),
	]),
	("编辑", [
		("KEY_LEFTCTRL+KEY_C", "复制"),
		("KEY_LEFTCTRL+KEY_V", "粘贴"),
		("KEY_LEFTCTRL+KEY_X", "剪切"),
		("KEY_LEFTCTRL+KEY_Z", "撤销"),
		("KEY_LEFTCTRL+KEY_A", "全选"),
		("KEY_LEFTCTRL+KEY_S", "保存"),
		("KEY_LEFTCTRL+KEY_F", "查找"),
	]),
	("功能键", [(f"KEY_F{n}", f"F{n}") for n in range(1, 25)]),
	("语音", [
		("atvv:toggle", "开/关遥控器麦克风"),
		("atvv:hold", "按住时开遥控器麦克风"),
		("atvv:hold & KEY_RIGHTALT+KEY_0", "按住说话：Vokie（右Alt+0）"),
		("atvv:hold & KEY_F9", "按住说话：vocotype（F9）"),
	]),
	("命令", [
		("cmd:xdg-open https://www.youtube.com", "打开 YouTube"),
		("cmd:xdg-open https://www.netflix.com", "打开 Netflix"),
		("cmd:loginctl lock-session", "锁定会话"),
	]),
]
ACTION_LABELS = {action: label for _, actions in MAPPING_GROUPS for action, label in actions}
ACTION_LABELS.update({"none": "不映射", "atvv:open": "打开遥控器麦克风", "atvv:close": "关闭遥控器麦克风"})
# Every key the daemon's uinput device can emit, minus range markers; offered by the advanced editor's completer.
ALL_KEYS = sorted(n for n in daemon.ecodes.ecodes if n.startswith(("KEY_", "BTN_")) and n not in ("KEY_MAX", "KEY_CNT", "KEY_RESERVED", "KEY_MIN_INTERESTING", "BTN_MISC"))
KEY_NAMES = {
	"LEFTCTRL": "Ctrl",
	"RIGHTCTRL": "右Ctrl",
	"LEFTALT": "Alt",
	"RIGHTALT": "右Alt",
	"LEFTSHIFT": "Shift",
	"RIGHTSHIFT": "右Shift",
	"LEFTMETA": "Meta",
	"RIGHTMETA": "右Meta",
	"ENTER": "回车",
	"ESC": "Esc",
	"SPACE": "空格",
	"BACKSPACE": "退格",
	"LEFT": "←",
	"RIGHT": "→",
	"UP": "↑",
	"DOWN": "↓",
}
MODIFIER_KEYS = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_LEFTMETA", "KEY_RIGHTMETA"}

# atvvoice command-line flags the console reads and rewrites (regex for the flag name, value follows after a space or '=').
GAIN_FLAG = r"(?:-g|--gain)"
HIGHPASS_FLAG = r"--highpass"
FADE_IN_FLAG = r"--fade-in"

# Recommended audio settings for the Chromecast Voice Remote (measured 2026-10-05): 8 dB keeps close speech under
# clipping, an 80 Hz high-pass removes the mic's power-up "pop" and DC offset, a 20 ms fade-in hides the first step.
RECOMMENDED_GAIN_DB = 8
RECOMMENDED_HIGHPASS_HZ = 80
RECOMMENDED_FADE_IN_MS = 20


def asset(name):
	"""An image from the install dir (assets/) or, running from a checkout, from the repository's Resources and Design folders."""
	for directory in ("assets", "../Resources/RemoteImages", "../Design/vRemoter-Logo-v1"):
		path = os.path.join(HERE, directory, name)
		if os.path.exists(path):
			return path
	return ""


def run(*cmd, timeout=3):
	"""Run a short command and return its stdout ('' on failure)."""
	try:
		return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
	except (OSError, subprocess.TimeoutExpired):
		return ""


def bt_connected(address):
	"""Whether BlueZ has the device connected on any adapter (adapter names change when a USB dongle is re-plugged)."""
	if not address:
		return False
	device = "dev_" + address.replace(":", "_")
	for path in run("busctl", "tree", "org.bluez", "--list").split():
		if path.endswith("/" + device) and "true" in run("busctl", "get-property", "org.bluez", path, "org.bluez.Device1", "Connected"):
			return True
	return False


# unit -> monotonic time of the last restart we issued; the status panel shows 重启中 instead of a failure during the grace period.
RESTARTED = {}
RESTART_GRACE = 10  # seconds: the 2 s stop/start gap plus atvvoice reconnecting to the remote


def restart_service(unit):
	RESTARTED[unit] = time.monotonic()
	# Stop, wait, start: an immediate restart of atvvoice can race BlueZ releasing its exclusive notify handles.
	subprocess.Popen(["sh", "-c", f"systemctl --user stop {unit}; sleep 2; systemctl --user start {unit}"], start_new_session=True)


def restarting(unit, check):
	"""Replace a failing check with 重启中 while a restart we issued is still within its grace period."""
	if check[0] != "good" and time.monotonic() - RESTARTED.get(unit, -RESTART_GRACE) < RESTART_GRACE:
		return ("busy", "重启中…")
	return check


def flag_value(command, flag):
	"""Numeric value of a flag in an atvvoice command line, or None when absent."""
	match = re.search(rf"(?:^|\s){flag}[ =]([0-9.]+)", command)
	return float(match.group(1)) if match else None


def strip_flag(command, flag):
	return re.sub(rf"\s{flag}[ =][0-9.]+", "", command)


def dbfs(value):
	return 20 * math.log10(value / 32768) if value > 0 else -120.0


def pw_record_args():
	"""pw-record arguments for headerless s16 on stdout; --raw only exists from PipeWire 1.2, and 1.0 (Ubuntu 24.04) rejects it but already writes raw."""
	try:
		help_text = subprocess.run(["pw-record", "--help"], capture_output=True, text=True, timeout=3)
		raw = "--raw" in help_text.stdout + help_text.stderr
	except (OSError, subprocess.TimeoutExpired):
		raw = False
	return ["--target", SOURCE_NAME, "--rate", str(SAMPLE_RATE), "--channels", "1", "--format", "s16"] + (["--raw"] if raw else []) + ["-"]


def toml_string(value):
	return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def spec_to_text(spec):
	return " & ".join(spec) if isinstance(spec, list) else spec


def text_to_spec(text):
	parts = [p.strip() for p in text.split("&") if p.strip()]
	return parts if len(parts) > 1 else (parts[0] if parts else "none")


def key_label(combo):
	"""KEY_LEFTCTRL+KEY_T -> Ctrl+T."""
	names = []
	for key in combo.split("+"):
		name = key.strip().removeprefix("KEY_")
		names.append(KEY_NAMES.get(name, name.capitalize() if len(name) > 3 and not name[1:].isdigit() else name))
	return "+".join(names)


def action_label(spec):
	"""What the editor shows for a button's configured action, e.g. ["atvv:hold", "KEY_F9"] -> 按住说话：vocotype（F9）."""
	text = spec_to_text(spec)
	if text in ACTION_LABELS:
		return ACTION_LABELS[text]
	parts = [p.strip() for p in text.split("&") if p.strip()]
	labels = []
	for part in parts:
		if part in ACTION_LABELS:
			labels.append(ACTION_LABELS[part] if part != "atvv:hold" else "开麦")
		elif part.startswith("cmd:"):
			labels.append(f"命令 {part[4:].strip()}")
		else:
			labels.append(ACTION_LABELS.get(part, key_label(part)))
	if len(labels) > 1 and "atvv:hold" in parts:
		return "按住开麦 + " + " + ".join(label for part, label in zip(parts, labels) if part != "atvv:hold")
	return " + ".join(labels)


def read_config(path):
	"""Raw button specs, voice settings and general settings from the daemon config, defaults filled in."""
	buttons = dict(daemon.DEFAULT_BUTTONS)
	voice = dict(daemon.DEFAULT_VOICE)
	general = dict(daemon.DEFAULT_GENERAL)
	if os.path.exists(path):
		with open(path, "rb") as f:
			data = daemon.tomllib.load(f)
		buttons.update(data.get("buttons", {}))
		voice.update(data.get("voice", {}))
		general.update(data.get("general", {}))
	return buttons, voice, general


def write_config(path, buttons, voice, general):
	lines = ["# vRemoter for Linux configuration (written by vremoter_gui.py; see config.example.toml for the syntax).", "", "[general]"]
	lines += [f"enabled = {'true' if general.get('enabled', True) else 'false'}", "", "[buttons]"]
	for name, spec in buttons.items():
		value = "[" + ", ".join(toml_string(p) for p in spec) + "]" if isinstance(spec, list) else toml_string(spec)
		lines.append(f"{name} = {value}")
	lines += ["", "[voice]"] + [f"{k} = {str(v).lower() if isinstance(v, bool) else toml_string(str(v))}" for k, v in voice.items()]
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		f.write("\n".join(lines) + "\n")


class Atvv:
	"""ATVVoice D-Bus access on the session bus."""

	def __init__(self):
		self.bus = QtDBus.QDBusConnection.sessionBus()

	def iface(self):
		return QtDBus.QDBusInterface(ATVV_SERVICE, daemon.ATVV_PATH, daemon.ATVV_INTERFACE, self.bus)

	def get(self, prop):
		# QDBusInterface.property() returns None for remote properties in PyQt6; use Properties.Get explicitly.
		message = QtDBus.QDBusMessage.createMethodCall(ATVV_SERVICE, daemon.ATVV_PATH, "org.freedesktop.DBus.Properties", "Get")
		message.setArguments([daemon.ATVV_INTERFACE, prop])
		reply = self.bus.call(message, QtDBus.QDBus.CallMode.Block, 1000)
		if reply.type() != QtDBus.QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
			return None
		return str(reply.arguments()[0])

	def state(self):
		return self.get("State") or "unavailable"

	def device_address(self):
		return self.get("DeviceAddress") or ""

	def call(self, method):
		reply = self.iface().call(method)
		return reply.errorMessage() if reply.type() == QtDBus.QDBusMessage.MessageType.ErrorMessage else ""


# ── Building blocks ────────────────────────────────────────────────────────────────────────────────────────────────────────


def label(text, name=None, wrap=False):
	widget = QLabel(text)
	if name:
		widget.setObjectName(name)
	widget.setWordWrap(wrap)
	return widget


def card(name="card"):
	frame = QFrame()
	frame.setObjectName(name)
	return frame


def card_header(title, subtitle=None):
	box = QVBoxLayout()
	box.setSpacing(2)
	box.addWidget(label(title, "cardTitle"))
	if subtitle:
		box.addWidget(label(subtitle, "caption", wrap=True))
	return box


class Dot(QWidget):
	"""A small status dot in one of the theme colours."""

	def __init__(self, color=TERTIARY, size=10):
		super().__init__()
		self.color = QColor(color)
		self.setFixedSize(size + 4, size + 4)

	def set_color(self, color):
		self.color = QColor(color)
		self.update()

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		p.setPen(Qt.PenStyle.NoPen)
		p.setBrush(self.color)
		p.drawEllipse(QRectF(2, 2, self.width() - 4, self.height() - 4))


class ToggleSwitch(QAbstractButton):
	"""The Mac-style pill switch (blue when on)."""

	def __init__(self):
		super().__init__()
		self.setCheckable(True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setFixedSize(46, 26)

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		on = self.isChecked()
		p.setPen(Qt.PenStyle.NoPen)
		p.setBrush(QColor("#3478F6" if on else "#3A3D42") if self.isEnabled() else QColor(LINE_SOFT))
		p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
		p.setBrush(QColor("#FFFFFF" if self.isEnabled() else TERTIARY))
		p.drawEllipse(QRectF(22 if on else 3, 3, 20, 20))


class Segmented(QFrame):
	"""Header page switcher: checkable buttons on a black rounded track."""

	def __init__(self, items, on_select):
		super().__init__()
		self.setObjectName("segment")
		layout = QHBoxLayout(self)
		layout.setContentsMargins(4, 4, 4, 4)
		layout.setSpacing(2)
		self.group = QButtonGroup(self)
		self.group.setExclusive(True)
		for index, text in enumerate(items):
			button = QPushButton(text)
			button.setObjectName("seg")
			button.setCheckable(True)
			button.setCursor(Qt.CursorShape.PointingHandCursor)
			self.group.addButton(button, index)
			layout.addWidget(button)
		self.group.idClicked.connect(on_select)
		self.group.button(0).setChecked(True)

	def select(self, index):
		self.group.button(index).setChecked(True)


class LedMeter(QWidget):
	"""Segmented level meter as on the Mac channel strips (−60..0 dBFS), with 低/高 marks drawn by the caller."""

	def __init__(self, segments=14, color=GREEN):
		super().__init__()
		self.segments = segments
		self.color = QColor(color)
		self.db = -120.0
		self.setFixedHeight(30)
		self.setMinimumWidth(200)

	def set_db(self, db):
		self.db = db
		self.update()

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		gap = 5
		w = (self.width() - gap * (self.segments - 1)) / self.segments
		lit = 0 if self.db <= -60 else math.ceil((self.db + 60) / 60 * self.segments)
		for i in range(self.segments):
			x = i * (w + gap)
			if i < lit:
				color = QColor(RED) if i >= self.segments - 1 else QColor(AMBER) if i >= self.segments - 3 else self.color
			else:
				color = QColor(BLACK)
			p.setPen(Qt.PenStyle.NoPen)
			p.setBrush(color)
			p.drawRoundedRect(QRectF(x, 0, w, self.height()), 3, 3)


class RemoteView(QWidget):
	"""The remote's product picture with a hotspot per button: click to select, flash on press, mark keys already tested."""

	clicked = pyqtSignal(str)

	def __init__(self, interactive=True):
		super().__init__()
		self.pixmap = QPixmap(asset("chromecast-voice-remote.png"))
		self.selected = None
		self.tested = set()
		self.flash = {}  # button -> time of last press
		self.interactive = interactive
		self.setMinimumSize(150, 400)
		self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
		if interactive:
			self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.fade = QTimer(self)
		self.fade.timeout.connect(self.update)

	def sizeHint(self):
		return QSize(190, 520)

	def geometry_for(self):
		"""Scale and offset that fit the picture into the widget, centred."""
		if self.pixmap.isNull():
			return 1.0, 0.0, 0.0
		scale = min(self.width() / self.pixmap.width(), (self.height() - 8) / self.pixmap.height())
		x0 = (self.width() - self.pixmap.width() * scale) / 2
		y0 = (self.height() - self.pixmap.height() * scale) / 2
		return scale, x0, y0

	def hotspot_rect(self, name):
		scale, x0, y0 = self.geometry_for()
		cx, cy, r = REMOTE_HOTSPOTS[name]
		return QRectF(x0 + (cx - r) * scale, y0 + (cy - r) * scale, 2 * r * scale, 2 * r * scale)

	def pressed(self, name):
		self.flash[name] = time.monotonic()
		self.fade.start(40)
		self.update()

	def mousePressEvent(self, event):
		if not self.interactive:
			return
		for name in REMOTE_HOTSPOTS:
			if self.hotspot_rect(name).contains(event.position()):
				self.clicked.emit(name)
				return

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
		if self.pixmap.isNull():
			p.setPen(QColor(SECONDARY))
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "找不到遥控器图片")
			return
		scale, x0, y0 = self.geometry_for()
		p.drawPixmap(QRectF(x0, y0, self.pixmap.width() * scale, self.pixmap.height() * scale), self.pixmap, QRectF(self.pixmap.rect()))
		now = time.monotonic()
		for name in REMOTE_HOTSPOTS:
			rect = self.hotspot_rect(name)
			if name in self.tested:
				p.setPen(QPen(QColor(GREEN), 2.5))
				p.setBrush(QColor(79, 209, 135, 45))
				p.drawEllipse(rect)
			age = now - self.flash.get(name, -10)
			if age < 0.8:
				alpha = int(200 * (1 - age / 0.8))
				p.setPen(Qt.PenStyle.NoPen)
				p.setBrush(QColor(79, 209, 135, alpha))
				p.drawEllipse(rect.adjusted(-4, -4, 4, 4))
			if name == self.selected:
				p.setPen(QPen(QColor(AMBER), 3))
				p.setBrush(Qt.BrushStyle.NoBrush)
				p.drawEllipse(rect.adjusted(-3, -3, 3, 3))
		if not any(now - t < 0.8 for t in self.flash.values()):
			self.fade.stop()


def button_icon(name, size=22):
	"""A round crop of the button from the remote picture, or a text glyph where a crop would be ambiguous."""
	if name in BUTTON_GLYPHS:
		return None
	source = QPixmap(asset("chromecast-voice-remote.png"))
	if source.isNull():
		return None
	cx, cy, r = REMOTE_HOTSPOTS[name]
	crop = source.copy(int(cx - r), int(cy - r), int(2 * r), int(2 * r)).scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
	icon = QPixmap(size * 2, size * 2)
	icon.fill(Qt.GlobalColor.transparent)
	p = QPainter(icon)
	p.setRenderHint(QPainter.RenderHint.Antialiasing)
	path = QPainterPath()
	path.addEllipse(QRectF(0, 0, size * 2, size * 2))
	p.setClipPath(path)
	p.drawPixmap(0, 0, crop)
	p.end()
	icon.setDevicePixelRatio(2)
	return icon


class StatusLine(QWidget):
	"""One row of the status panel: dot, name, value, and a fix button shown only while the check fails."""

	def __init__(self, name, action_text=None, on_action=None):
		super().__init__()
		layout = QHBoxLayout(self)
		layout.setContentsMargins(4, 5, 4, 5)
		layout.setSpacing(10)
		self.dot = Dot(TERTIARY)
		self.name = label(name, "secondary")
		self.name.setMinimumWidth(130)
		self.value = label("—")
		self.value.setStyleSheet("font-weight: 600;")
		layout.addWidget(self.dot)
		layout.addWidget(self.name)
		layout.addWidget(self.value, 1)
		self.button = None
		if action_text:
			self.button = QPushButton(action_text)
			self.button.setCursor(Qt.CursorShape.PointingHandCursor)
			self.button.clicked.connect(on_action)
			self.button.hide()
			layout.addWidget(self.button)

	def set(self, state, value):
		"""state: 'good', 'warn', 'bad' or 'busy' (a fix is already under way, so no button)."""
		self.dot.set_color({"good": GREEN, "warn": AMBER, "bad": RED, "busy": AMBER}[state])
		self.value.setText(value)
		if self.button:
			self.button.setVisible(state in ("warn", "bad"))


# ── Audio page ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


class LevelMeter(QWidget):
	"""Scrolling level history (newest on the right) next to a peak meter with peak hold and a clip lamp, in dBFS."""

	FLOOR = -60.0
	BLOCK = SAMPLE_RATE // 20  # 50 ms per history column
	HISTORY = 15  # seconds kept on screen
	HOLD = 1.5  # seconds the peak-hold marker stays before falling
	GRID = (-6, -12, -20, -30, -40, -50)
	METER_WIDTH = 22
	LABEL_WIDTH = 34
	TAKE_AVG = QColor("#4cc9f0")  # per-recording average (RMS) line
	TAKE_PEAK = QColor("#f472b6")  # per-recording peak line

	def __init__(self):
		super().__init__()
		self.setMinimumHeight(170)
		self.history = collections.deque(maxlen=self.HISTORY * SAMPLE_RATE // self.BLOCK)  # (rms_db, peak_db, recording, mean_square, peak)
		self.block = array.array("h")
		self.rms_db = self.peak_db = self.hold_db = self.FLOOR
		self.hold_since = 0.0
		self.clip_until = 0.0
		self.live = False  # history scrolls only while the remote mic streams; it holds still in between

	def set_live(self, live):
		if self.live and not live and self.history and self.history[-1] is not None:
			self.history.append(None)  # stop mark: closes this mic session off from the next
		self.live = live
		self.update()

	def reset(self):
		self.history.clear()
		self.block = array.array("h")
		self.rms_db = self.peak_db = self.hold_db = self.FLOOR
		self.update()

	def feed(self, chunk, recording):
		self.block.extend(chunk)
		while len(self.block) >= self.BLOCK:
			block, self.block = self.block[:self.BLOCK], self.block[self.BLOCK:]
			peak = max(abs(s) for s in block)
			mean_square = sum(s * s for s in block) / len(block)
			self.rms_db = max(self.FLOOR, dbfs(math.sqrt(mean_square)))
			self.peak_db = max(self.FLOOR, dbfs(peak))
			if self.live:
				self.history.append((self.rms_db, self.peak_db, recording, mean_square, peak))
			now = time.monotonic()
			if self.peak_db >= self.hold_db or now - self.hold_since > self.HOLD:
				self.hold_db, self.hold_since = self.peak_db, now
			if peak >= 32760:
				self.clip_until = now + self.HOLD
			self.update()

	def recorded_runs(self):
		"""(first, last) history indices of each unbroken recorded stretch."""
		runs, first = [], None
		for i, entry in enumerate(self.history):
			if entry is not None and entry[2]:
				if first is None:
					first = i
			elif first is not None:
				runs.append((first, i - 1))
				first = None
		if first is not None:
			runs.append((first, len(self.history) - 1))
		return runs

	def y_of(self, db, top, height):
		return top + height * min(1.0, max(0.0, db / self.FLOOR))

	@staticmethod
	def zone_color(db):
		return QColor(RED) if db > -3 else QColor(AMBER) if db > -12 else QColor(GREEN)

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
		w, h = self.width(), self.height()
		top, height = 6, h - 22
		graph_left, graph_right = self.LABEL_WIDTH, w - self.METER_WIDTH - 10
		p.fillRect(self.rect(), QColor("#0B0C0E"))

		# Grid and dB labels.
		p.setFont(QFont("monospace", 7))
		for db in self.GRID:
			y = int(self.y_of(db, top, height))
			p.setPen(QPen(QColor("#2A2D33"), 1, Qt.PenStyle.DotLine))
			p.drawLine(graph_left, y, graph_right, y)
			p.setPen(QColor(TERTIARY))
			p.drawText(0, y - 6, self.LABEL_WIDTH - 4, 12, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(db))

		# History: one column per block, RMS filled, peak as a thin cap; recorded stretches shaded behind.
		columns = self.history.maxlen
		col_w = (graph_right - graph_left) / columns
		bottom = top + height
		start = columns - len(self.history)
		for i, entry in enumerate(self.history):
			x = graph_left + (start + i) * col_w
			if entry is None:
				p.fillRect(QRectF(x + col_w / 2 - 0.5, top, 1, height), QColor("#4A4F57"))
				continue
			rms_db, peak_db, recording = entry[:3]
			if recording:
				p.fillRect(QRectF(x, top, col_w + 0.5, height), QColor(240, 84, 87, 36))
			y_rms = self.y_of(rms_db, top, height)
			p.fillRect(QRectF(x, y_rms, col_w + 0.5, bottom - y_rms), self.zone_color(rms_db))
			y_peak = self.y_of(peak_db, top, height)
			p.fillRect(QRectF(x, y_peak, col_w + 0.5, 1.5), self.zone_color(peak_db).lighter(140))

		# Each recorded stretch gets its own average and peak, the same two figures as its entry in the recordings list.
		p.setFont(QFont("monospace", 7))
		for first, last in self.recorded_runs():
			blocks = [self.history[i] for i in range(first, last + 1)]
			avg_db = max(self.FLOOR, dbfs(math.sqrt(sum(b[3] for b in blocks) / len(blocks))))
			peak_db = max(self.FLOOR, dbfs(max(b[4] for b in blocks)))
			x0, x1 = graph_left + (start + first) * col_w, graph_left + (start + last + 1) * col_w
			chips = []
			for db, color, name, above in ((peak_db, self.TAKE_PEAK, "峰", True), (avg_db, self.TAKE_AVG, "均", False)):
				y = self.y_of(db, top, height)
				p.fillRect(QRectF(x0, y - 1, x1 - x0, 2), color)
				if x1 - x0 <= 48:
					continue
				# Peak value above its line and average below its, flipped to the other side when that would leave the graph,
				# and moved left of the other chip if the two would overlap; on a dark chip so the bars don't swallow them.
				text = f"{name} {round(db)}"
				tw = p.fontMetrics().horizontalAdvance(text) + 6
				chip_y = y - 14 if above else y + 2
				if chip_y < top:
					chip_y = y + 2
				elif chip_y + 12 > bottom:
					chip_y = y - 14
				chip = QRectF(x1 - tw - 2, chip_y, tw, 12)
				for other in chips:
					if chip.intersects(other):
						chip.moveRight(other.left() - 4)
				chips.append(chip)
				p.fillRect(chip, QColor(11, 12, 14, 220))
				p.setPen(color)
				p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)

		# Time axis and legend.
		p.setPen(QColor(TERTIARY))
		p.drawText(graph_left, bottom + 2, 120, 14, Qt.AlignmentFlag.AlignLeft, f"-{self.HISTORY} 秒")
		p.drawText(graph_right - 60, bottom + 2, 60, 14, Qt.AlignmentFlag.AlignRight, "现在")
		legend_x = graph_left + (graph_right - graph_left) // 2 - 80
		for i, (color, name) in enumerate(((self.TAKE_AVG, "录音段平均"), (self.TAKE_PEAK, "录音段峰值"))):
			x = legend_x + i * 90
			p.fillRect(QRectF(x, bottom + 8, 14, 2), color)
			p.setPen(QColor(TERTIARY))
			p.drawText(x + 18, bottom + 2, 70, 14, Qt.AlignmentFlag.AlignLeft, name)
		if not self.live:
			p.drawText(graph_left + 6, top, 200, 14, Qt.AlignmentFlag.AlignLeft, "未开麦，历史已暂停")

		# Peak meter: zones dimmed, lit up to the current peak, RMS as a lighter inner bar, hold marker, clip lamp.
		mx = w - self.METER_WIDTH - 4
		for lo, hi in ((self.FLOOR, -12), (-12, -3), (-3, 0)):
			y_hi, y_lo = self.y_of(hi, top, height), self.y_of(lo, top, height)
			color = self.zone_color(hi - 0.1)
			p.fillRect(QRectF(mx, y_hi, self.METER_WIDTH, y_lo - y_hi), color.darker(450))
			lit_top = max(y_hi, self.y_of(self.peak_db, top, height))
			if lit_top < y_lo:
				p.fillRect(QRectF(mx, lit_top, self.METER_WIDTH, y_lo - lit_top), color)
		y_rms = self.y_of(self.rms_db, top, height)
		p.fillRect(QRectF(mx + self.METER_WIDTH / 3, y_rms, self.METER_WIDTH / 3, bottom - y_rms), QColor(255, 255, 255, 90))
		if self.hold_db > self.FLOOR:
			p.fillRect(QRectF(mx, self.y_of(self.hold_db, top, height) - 1, self.METER_WIDTH, 2), QColor("#ffffff"))
		clipped = time.monotonic() < self.clip_until
		p.fillRect(QRectF(mx, bottom + 4, self.METER_WIDTH, 10), QColor(RED) if clipped else QColor(RED_DEEP))
		p.end()


class AudioPage(QWidget):
	"""Remote mic strip with level history, ATVVoice audio processing, status checks and recordings."""

	BADGE_STYLE = "background: {bg}; color: {fg}; font-weight: 700; padding: 6px 14px; border-radius: 13px;"

	def __init__(self, atvv, on_take, on_recording_changed):
		super().__init__()
		self.setObjectName("page")
		self.atvv = atvv
		self.on_take = on_take
		self.on_recording_changed = on_recording_changed
		self.capture = None
		self.recording = False
		self.manual = False
		self.streaming = False
		self.samples = array.array("h")
		self.pending = b""
		self.player = None
		self.last_level = -120.0
		self.capture_args = pw_record_args()
		os.makedirs(RECORDINGS_DIR, exist_ok=True)
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(16)

		# Mixer card: the channel strip on the left, the level history on the right.
		mixer = card()
		mixer.setMinimumHeight(340)
		mixer_layout = QHBoxLayout(mixer)
		mixer_layout.setContentsMargins(22, 20, 22, 20)
		mixer_layout.setSpacing(22)
		strip = QVBoxLayout()
		strip.setSpacing(8)
		strip.addWidget(label("遥控器麦克风", "title"))
		strip.addWidget(label("Chromecast 语音遥控器", "subtitle"))
		strip.addSpacing(8)
		status = QHBoxLayout()
		self.state_dot = Dot(TERTIARY)
		self.state_text = label("未连接", "secondary")
		self.db_text = label("−∞ dB", "mono")
		status.addWidget(self.state_dot)
		status.addWidget(self.state_text, 1)
		status.addWidget(self.db_text)
		strip.addLayout(status)
		self.led = LedMeter(12, GREEN)
		strip.addWidget(self.led)
		lowhigh = QHBoxLayout()
		lowhigh.addWidget(label("低", "caption"))
		lowhigh.addStretch(1)
		lowhigh.addWidget(label("高", "caption"))
		strip.addLayout(lowhigh)
		strip.addSpacing(10)
		buttons = QHBoxLayout()
		self.record_button = QPushButton("● 开麦并录音")
		self.record_button.setObjectName("record")
		self.record_button.setCheckable(True)
		self.record_button.setCursor(Qt.CursorShape.PointingHandCursor)
		self.record_button.toggled.connect(self.toggle_manual)
		self.record_button.setMinimumHeight(42)
		buttons.addWidget(self.record_button)
		buttons.addStretch(1)
		strip.addLayout(buttons)
		self.auto = QCheckBox("语音键 / 按住开麦时自动录音")
		self.auto.setChecked(True)
		strip.addWidget(self.auto)
		self.mute_output = QCheckBox("录音时静音输出")
		self.mute_output.setToolTip("立即保存。开麦时静音当前默认输出，结束后恢复；原本已静音的输出保持静音。")
		self.mute_output.setChecked(read_config(daemon.DEFAULT_CONFIG_PATH)[1]["mute_output"])
		self.mute_output.toggled.connect(self.save_output_mute)
		strip.addWidget(self.mute_output)
		strip.addStretch(1)
		# Recording badge, always in place so nothing shifts: grey when idle, a blinking red pill with the elapsed time while recording.
		self.rec_badge = QLabel()
		self.rec_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.rec_badge.setFixedHeight(30)
		self.rec_badge.setMinimumWidth(self.rec_badge.fontMetrics().horizontalAdvance("● 录音中  888.8 秒") + 50)
		self.set_badge_idle()
		self.rec_started = 0.0
		self.rec_blink = QTimer(self)
		self.rec_blink.timeout.connect(self.update_badge)
		strip.addWidget(self.rec_badge, 0, Qt.AlignmentFlag.AlignLeft)
		strip_widget = QWidget()
		strip_widget.setLayout(strip)
		strip_widget.setFixedWidth(290)
		mixer_layout.addWidget(strip_widget)
		divider = QFrame()
		divider.setObjectName("vline")
		mixer_layout.addWidget(divider)
		history = QVBoxLayout()
		history.setSpacing(8)
		top_row = QHBoxLayout()
		top_row.addLayout(card_header("电平历史", "最近 15 秒 · 红底为录音段"))
		top_row.addStretch(1)
		self.meter_text = label("未开麦时为静音", "mono")
		top_row.addWidget(self.meter_text, 0, Qt.AlignmentFlag.AlignTop)
		history.addLayout(top_row)
		self.meter = LevelMeter()
		history.addWidget(self.meter, 1)
		mixer_layout.addLayout(history, 1)
		layout.addWidget(mixer)

		# Audio processing.
		processing = card()
		processing_layout = QHBoxLayout(processing)
		processing_layout.setContentsMargins(22, 16, 22, 16)
		processing_layout.setSpacing(14)
		processing_layout.addLayout(card_header("音频处理", "ATVVoice · 应用后会重启麦克风服务"))
		processing_layout.addSpacing(10)
		command = self.atvv_command()
		self.gain = QSpinBox()
		self.gain.setRange(0, 40)
		self.gain.setSuffix(" dB")
		self.gain.setValue(int(flag_value(command, GAIN_FLAG) or 20))  # ATVVoice's own default
		self.highpass_on = QCheckBox("高通滤波")
		self.highpass_on.setToolTip("去掉遥控器麦克风上电时约 250 ms 的直流衰减（开头的「噗」声）和残留的直流偏移")
		self.highpass = QSpinBox()
		self.highpass.setRange(20, 300)
		self.highpass.setSuffix(" Hz")
		self.fade_in_on = QCheckBox("淡入")
		self.fade_in_on.setToolTip("每次开麦时从静音渐入，去掉第一帧的台阶")
		self.fade_in = QSpinBox()
		self.fade_in.setRange(1, 200)
		self.fade_in.setSuffix(" ms")
		filters = ((self.highpass_on, self.highpass, HIGHPASS_FLAG, RECOMMENDED_HIGHPASS_HZ), (self.fade_in_on, self.fade_in, FADE_IN_FLAG, RECOMMENDED_FADE_IN_MS))
		for check, spin, flag, default in filters:
			value = flag_value(command, flag) or 0
			check.setChecked(value > 0)
			spin.setValue(int(value) if value > 0 else default)
			spin.setEnabled(value > 0)
			check.toggled.connect(spin.setEnabled)
		if not self.atvv_supports_filters(command):
			for widget in (self.highpass_on, self.highpass, self.fade_in_on, self.fade_in):
				widget.setEnabled(False)
				widget.setToolTip("当前安装的 ATVVoice 不支持 --highpass / --fade-in，请更新到 fix/htt-voice-gesture 分支的版本")
		processing_layout.addWidget(label("增益", "secondary"))
		processing_layout.addWidget(self.gain)
		processing_layout.addSpacing(8)
		processing_layout.addWidget(self.highpass_on)
		processing_layout.addWidget(self.highpass)
		processing_layout.addSpacing(8)
		processing_layout.addWidget(self.fade_in_on)
		processing_layout.addWidget(self.fade_in)
		processing_layout.addStretch(1)
		reset_audio = QPushButton("重置")
		reset_audio.setToolTip(f"恢复推荐值：增益 {RECOMMENDED_GAIN_DB} dB、高通 {RECOMMENDED_HIGHPASS_HZ} Hz、淡入 {RECOMMENDED_FADE_IN_MS} ms（点「应用」后生效）")
		reset_audio.clicked.connect(self.reset_audio)
		apply_gain = QPushButton("应用")
		apply_gain.setObjectName("primary")
		apply_gain.clicked.connect(self.apply_gain)
		processing_layout.addWidget(reset_audio)
		processing_layout.addWidget(apply_gain)
		layout.addWidget(processing)

		# Status checks and recordings side by side.
		bottom = QHBoxLayout()
		bottom.setSpacing(16)
		checks = card()
		checks_layout = QVBoxLayout(checks)
		checks_layout.setContentsMargins(22, 16, 22, 14)
		checks_layout.addLayout(card_header("状态检查", "每 2 秒刷新；未通过的项可以直接处理"))
		checks_layout.addSpacing(4)
		self.bt_row = StatusLine("遥控器连接", "唤醒提示", self.wake_tip)
		self.atvv_row = StatusLine("麦克风服务", "重启", lambda: restart_service("atvvoice"))
		self.map_row = StatusLine("按键映射服务", "重启", lambda: restart_service("vremoter-linux"))
		self.mic_row = StatusLine("默认麦克风", "设为遥控器", lambda: run("pactl", "set-default-source", SOURCE_NAME))
		for row in (self.bt_row, self.atvv_row, self.map_row, self.mic_row):
			checks_layout.addWidget(row)
		checks_layout.addStretch(1)
		bottom.addWidget(checks, 1)
		takes = card()
		takes_layout = QVBoxLayout(takes)
		takes_layout.setContentsMargins(22, 16, 22, 16)
		takes_layout.addLayout(card_header("录音", RECORDINGS_DIR.replace(os.path.expanduser("~"), "~")))
		self.takes = QListWidget()
		self.takes.itemDoubleClicked.connect(self.play)
		takes_layout.addWidget(self.takes, 1)
		row = QHBoxLayout()
		row.addWidget(label("双击播放", "caption"))
		row.addStretch(1)
		play = QPushButton("播放所选")
		stop = QPushButton("停止播放")
		play.clicked.connect(lambda: self.play(self.takes.currentItem()))
		stop.clicked.connect(self.stop_playback)
		row.addWidget(play)
		row.addWidget(stop)
		takes_layout.addLayout(row)
		bottom.addWidget(takes, 1)
		layout.addLayout(bottom, 1)

		self.load_takes()
		self.start_capture()

	def wake_tip(self):
		QMessageBox.information(self, "唤醒遥控器", "按遥控器任意键唤醒它，它会自动回连。\n如果长时间连不上，按住「返回 + 主页」进入配对模式后用 vremoter-pair（源码安装用 pair-remote.sh）重新配对。")

	def set_checks(self, checks):
		for row, key in ((self.bt_row, "bt"), (self.atvv_row, "atvv"), (self.map_row, "map"), (self.mic_row, "mic")):
			row.set(*checks[key])

	def set_strip_state(self):
		if self.recording:
			color, text = RED, "录音中"
		elif self.streaming:
			color, text = GREEN, "有声音" if self.last_level > -50 else "已开麦"
		elif SOURCE_NAME in run("pactl", "list", "short", "sources"):
			color, text = GREEN, "已就绪 · 未开麦"
		else:
			color, text = TERTIARY, "未连接"
		self.state_dot.set_color(color)
		self.state_text.setText(text)

	# Capture runs continuously for the meter; samples are kept only while recording.
	def start_capture(self):
		if SOURCE_NAME not in run("pactl", "list", "short", "sources"):
			# pw-record would silently fall back to another mic; wait for ATVVoice to publish the source.
			self.meter.reset()
			self.meter_text.setText("遥控器麦克风不存在，稍后自动重试")
			self.set_strip_state()
			QTimer.singleShot(2000, self.start_capture)
			return
		self.capture = QProcess(self)
		self.capture.readyReadStandardOutput.connect(self.read_capture)
		self.capture.finished.connect(self.capture_finished)
		self.capture.start("pw-record", self.capture_args)
		self.set_strip_state()

	def capture_finished(self, code, _status):
		if code != 0:
			error = bytes(self.capture.readAllStandardError()).decode(errors="replace").strip().splitlines()
			self.meter.reset()
			self.meter_text.setText(f"pw-record 退出（{code}）：{error[0] if error else '无输出'}，稍后重试")
		QTimer.singleShot(2000, self.start_capture)

	def read_capture(self):
		data = self.pending + bytes(self.capture.readAllStandardOutput())
		usable = len(data) - len(data) % 2
		self.pending = data[usable:]
		chunk = array.array("h", data[:usable])
		if not chunk:
			return
		if self.recording:
			self.samples.extend(chunk)
		peak = max(abs(s) for s in chunk)
		rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
		self.meter.feed(chunk, self.recording)
		self.last_level = dbfs(rms)
		self.led.set_db(self.last_level if self.streaming else -120)
		self.db_text.setText(f"{self.last_level:.0f} dB" if self.streaming and rms > 0 else "−∞ dB")
		self.meter_text.setText(f"平均 {dbfs(rms):6.1f}   峰值 {dbfs(peak):6.1f} dBFS")

	def toggle_manual(self, on):
		self.manual = on
		self.record_button.setText("■ 停止录音并关麦" if on else "● 开麦并录音")
		if on:
			error = self.atvv.call("MicOpen")
			if error:
				QMessageBox.warning(self, "开麦失败", error)
			self.begin()
		else:
			self.atvv.call("MicClose")
			self.end()

	def mic_state(self, state):
		self.streaming = state == "streaming"
		self.meter.set_live(self.streaming)
		if not self.streaming:
			self.led.set_db(-120)
			self.db_text.setText("−∞ dB")
		if not self.manual and self.auto.isChecked():
			if state == "streaming":
				self.begin()
			elif state in ("connected", "disconnected"):
				self.end()
		self.set_strip_state()

	def begin(self):
		if not self.recording:
			self.samples = array.array("h")
			self.recording = True
			self.rec_started = time.monotonic()
			self.rec_badge.setStyleSheet(self.BADGE_STYLE.format(bg=RED, fg="white"))
			self.update_badge()
			self.rec_blink.start(500)
			self.on_recording_changed(True)
			self.set_strip_state()

	def set_badge_idle(self):
		self.rec_badge.setStyleSheet(self.BADGE_STYLE.format(bg=BLACK, fg=TERTIARY))
		self.rec_badge.setText("○ 未录音")

	def update_badge(self):
		elapsed = time.monotonic() - self.rec_started
		dot = "●" if int(elapsed * 2) % 2 == 0 else "○"
		self.rec_badge.setText(f"{dot} 录音中  {elapsed:4.1f} 秒")

	def end(self):
		if not self.recording:
			return
		self.recording = False
		self.rec_blink.stop()
		self.set_badge_idle()
		self.on_recording_changed(False)
		self.set_strip_state()
		if len(self.samples) < SAMPLE_RATE // 10:
			return
		path = os.path.join(RECORDINGS_DIR, time.strftime("remote-%Y%m%d-%H%M%S.wav"))
		with wave.open(path, "wb") as w:
			w.setnchannels(1)
			w.setsampwidth(2)
			w.setframerate(SAMPLE_RATE)
			w.writeframes(self.samples.tobytes())
		self.on_take(self.add_take(path, self.samples, time.localtime()))

	def load_takes(self):
		"""List the recordings left by earlier sessions, oldest first so add_take() leaves the newest on top."""
		for name in sorted(os.listdir(RECORDINGS_DIR)):
			if not name.endswith(".wav"):
				continue
			path = os.path.join(RECORDINGS_DIR, name)
			try:
				with wave.open(path, "rb") as w:
					samples = array.array("h", w.readframes(w.getnframes()))
			except (OSError, EOFError, wave.Error):
				continue
			if samples:
				self.add_take(path, samples, time.localtime(os.path.getmtime(path)))

	def add_take(self, path, samples, when):
		peak = dbfs(max(abs(s) for s in samples))
		rms = dbfs(math.sqrt(sum(s * s for s in samples) / len(samples)))
		clipped = sum(1 for s in samples if abs(s) >= 32760)
		text = f"{time.strftime('%m-%d %H:%M:%S', when)}   {len(samples) / SAMPLE_RATE:4.1f} 秒   峰值 {peak:5.1f}   平均 {rms:5.1f} dBFS"
		if clipped:
			text += f"   ⚠ 削波 {clipped} 点"
		item = QListWidgetItem(text)
		item.setData(Qt.ItemDataRole.UserRole, path)
		if clipped:
			item.setForeground(QColor(AMBER))
		self.takes.insertItem(0, item)
		self.takes.setCurrentItem(item)
		return peak

	def play(self, item):
		if item is None:
			return
		self.stop_playback()
		self.player = QProcess(self)
		self.player.start("pw-play", [item.data(Qt.ItemDataRole.UserRole)])

	def stop_playback(self):
		if self.player and self.player.state() != QProcess.ProcessState.NotRunning:
			self.player.kill()

	@staticmethod
	def atvv_command():
		"""The effective atvvoice command line, whichever unit file or drop-in it comes from ('' if unknown)."""
		match = re.search(r"argv\[\]=([^;]*)", run("systemctl", "--user", "show", "atvvoice", "-p", "ExecStart", "--value"))
		return match.group(1).strip() if match else ""

	@staticmethod
	def atvv_supports_filters(command):
		"""Whether the installed atvvoice knows --highpass / --fade-in; passing them to an older one stops the service from starting."""
		binary = command.split()[0] if command else ""
		return bool(binary) and "--highpass" in run(binary, "--help")

	def save_output_mute(self, enabled):
		try:
			buttons, voice, general = read_config(daemon.DEFAULT_CONFIG_PATH)
			voice["mute_output"] = enabled
			write_config(daemon.DEFAULT_CONFIG_PATH, buttons, voice, general)
		except (OSError, daemon.tomllib.TOMLDecodeError) as e:
			self.mute_output.blockSignals(True)
			self.mute_output.setChecked(not enabled)
			self.mute_output.blockSignals(False)
			QMessageBox.warning(self, "无法保存静音设置", str(e))
			return
		restart_service("vremoter-linux")

	def reset_audio(self):
		"""Put the recommended values back in the controls; like the mapping page's reset, nothing changes until 应用."""
		self.gain.setValue(RECOMMENDED_GAIN_DB)
		self.highpass.setValue(RECOMMENDED_HIGHPASS_HZ)
		self.fade_in.setValue(RECOMMENDED_FADE_IN_MS)
		if self.highpass_on.isEnabled():
			self.highpass_on.setChecked(True)
			self.fade_in_on.setChecked(True)

	def apply_gain(self):
		command = self.atvv_command()
		if not command:
			QMessageBox.warning(self, "无法修改设置", "读不到 atvvoice 服务的启动命令（systemctl --user show atvvoice）")
			return
		for flag in (GAIN_FLAG, HIGHPASS_FLAG, FADE_IN_FLAG):
			command = strip_flag(command, flag)
		command += f" --gain {self.gain.value()}"
		if self.atvv_supports_filters(command):
			command += f" --highpass {self.highpass.value() if self.highpass_on.isChecked() else 0}"
			command += f" --fade-in {self.fade_in.value() if self.fade_in_on.isChecked() else 0}"
		# A drop-in leaves the installed unit alone; the empty ExecStart= clears the unit's own line first.
		os.makedirs(os.path.dirname(ATVV_OVERRIDE), exist_ok=True)
		with open(ATVV_OVERRIDE, "w") as f:
			f.write(f"[Service]\nExecStart=\nExecStart={command}\n")
		run("systemctl", "--user", "daemon-reload")
		restart_service("atvvoice")


# ── Mapping page ───────────────────────────────────────────────────────────────────────────────────────────────────────────


class KeyCaptureDialog(QDialog):
	"""Record a keyboard shortcut: hold the keys, release, then save. Keys come from the native scan code (evdev code + 8)."""

	def __init__(self, button_name, parent=None):
		super().__init__(parent)
		self.setWindowTitle("录制键盘按键")
		self.setModal(True)
		self.setMinimumWidth(420)
		self.held = []
		self.combo = []
		layout = QVBoxLayout(self)
		layout.setContentsMargins(24, 22, 24, 18)
		layout.setSpacing(12)
		layout.addWidget(label(f"为「{BUTTON_LABELS.get(button_name, button_name)}」录制按键", "cardTitle"))
		layout.addWidget(label("现在按下键盘按键或组合键（如 Ctrl+T），松开后确认。", "secondary", wrap=True))
		self.shown = label("等待按键…", "title")
		self.shown.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.shown.setMinimumHeight(70)
		box = card("inset")
		box_layout = QVBoxLayout(box)
		box_layout.addWidget(self.shown)
		layout.addWidget(box)
		self.with_mic = QCheckBox("按住时同时打开遥控器麦克风（用于语音输入法的按住说话）")
		layout.addWidget(self.with_mic)
		buttons = QHBoxLayout()
		buttons.addStretch(1)
		cancel = QPushButton("取消")
		cancel.clicked.connect(self.reject)
		self.save = QPushButton("保存映射")
		self.save.setObjectName("primary")
		self.save.setEnabled(False)
		self.save.clicked.connect(self.accept)
		for b in (cancel, self.save):
			b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep keys (Return, Esc) for the recording
			buttons.addWidget(b)
		layout.addLayout(buttons)

	def key_name(self, event):
		code = event.nativeScanCode() - 8
		return daemon.ecodes.KEY.get(code) if code > 0 else None

	def keyPressEvent(self, event):
		if event.isAutoRepeat():
			return
		name = self.key_name(event)
		if isinstance(name, list):
			name = name[0]
		if not name:
			return
		if not self.held:
			self.combo = []
		self.held.append(name)
		if name not in self.combo:
			self.combo.append(name)
		self.show_combo()

	def keyReleaseEvent(self, event):
		if event.isAutoRepeat():
			return
		name = self.key_name(event)
		if isinstance(name, list):
			name = name[0]
		if name in self.held:
			self.held.remove(name)
		if not self.held and self.combo:
			self.save.setEnabled(True)

	def show_combo(self):
		ordered = [k for k in self.combo if k in MODIFIER_KEYS] + [k for k in self.combo if k not in MODIFIER_KEYS]
		self.combo = ordered
		self.shown.setText(key_label("+".join(ordered)))

	def spec(self):
		combo = "+".join(self.combo)
		return ["atvv:hold", combo] if self.with_mic.isChecked() else combo


class MappingRow(QFrame):
	"""One button in the mapping list: picture crop or glyph, name, and the target as a drop-down menu."""

	selected = pyqtSignal(str)
	changed = pyqtSignal()

	def __init__(self, name, spec, completion):
		super().__init__()
		self.setObjectName("row")
		self.name = name
		self.spec = spec
		self.completion = completion
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		layout = QHBoxLayout(self)
		layout.setContentsMargins(12, 6, 8, 6)
		layout.setSpacing(12)
		icon = QLabel()
		icon.setFixedSize(26, 26)
		icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
		pixmap = button_icon(name)
		if pixmap:
			icon.setPixmap(pixmap)
		else:
			icon.setText(BUTTON_GLYPHS.get(name, "•"))
			icon.setStyleSheet(f"color: {SECONDARY}; font-size: 17px;")
		layout.addWidget(icon)
		layout.addWidget(label(BUTTON_LABELS.get(name, name)), 1)
		self.target = QPushButton()
		self.target.setObjectName("target")
		self.target.setMinimumWidth(240)
		self.target.setCursor(Qt.CursorShape.PointingHandCursor)
		if spec is None:
			# The voice key never reaches the HID device: ATVVoice handles it over the ATVV GATT service.
			self.target.setText("语音输入 · 短按开关 / 按住说话")
			self.target.setEnabled(False)
			self.target.setToolTip("由 ATVVoice 处理，不能映射")
		else:
			self.target.clicked.connect(self.open_menu)
			self.refresh()
		layout.addWidget(self.target)

	def refresh(self):
		self.target.setText(f"{action_label(self.spec)}   ⌄")
		self.target.setToolTip(spec_to_text(self.spec))

	def set_selected(self, on):
		self.setProperty("selected", "true" if on else "false")
		self.style().unpolish(self)
		self.style().polish(self)

	def mousePressEvent(self, _event):
		self.selected.emit(self.name)

	def set_spec(self, spec):
		self.spec = spec
		self.refresh()
		self.changed.emit()

	def open_menu(self):
		self.selected.emit(self.name)
		menu = QMenu(self)
		current = spec_to_text(self.spec)
		none = menu.addAction("不映射（屏蔽此键）")
		none.triggered.connect(lambda: self.set_spec("none"))
		menu.addSeparator()
		for group, actions in MAPPING_GROUPS:
			sub = menu.addMenu(group)
			for action, text in actions:
				item = sub.addAction(("✓ " if action == current else "   ") + text)
				item.setToolTip(action)
				item.triggered.connect(lambda _=False, a=action: self.set_spec(text_to_spec(a)))
		menu.addSeparator()
		record = menu.addAction("录制键盘按键…")
		record.triggered.connect(self.record)
		advanced = menu.addAction("高级：输入动作…")
		advanced.triggered.connect(self.advanced)
		menu.exec(self.target.mapToGlobal(self.target.rect().bottomLeft()))

	def record(self):
		dialog = KeyCaptureDialog(self.name, self.window())
		if isinstance(self.spec, list) and "atvv:hold" in self.spec:
			dialog.with_mic.setChecked(True)
		if dialog.exec():
			self.set_spec(dialog.spec())

	def advanced(self):
		dialog = QInputDialog(self.window())
		dialog.setWindowTitle("输入动作")
		dialog.setLabelText("按键（KEY_ENTER）、组合键（KEY_RIGHTALT+KEY_0）、cmd:命令、atvv:toggle / atvv:hold；多个动作用 & 连接。")
		dialog.setTextValue(spec_to_text(self.spec))
		dialog.resize(560, 140)
		edit = dialog.findChild(QLineEdit)
		if edit:
			edit.setCompleter(TokenCompleter(self.completion, edit))
		if dialog.exec():
			spec = text_to_spec(dialog.textValue())
			try:
				daemon.Target(spec)
			except ValueError as e:
				QMessageBox.warning(self, "动作无效", str(e))
				return
			self.set_spec(spec)


class TokenCompleter(QCompleter):
	"""Completes only the token after the last '+' or '&', so combos like KEY_LEFTCTRL+KEY_T can be typed piece by piece."""

	def __init__(self, model, line_edit):
		super().__init__(model, line_edit)
		self.line_edit = line_edit
		self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
		self.setFilterMode(Qt.MatchFlag.MatchContains)
		self.setMaxVisibleItems(15)

	def splitPath(self, path):
		return [re.split(r"[+&]", path)[-1].strip()]

	def pathFromIndex(self, index):
		text = self.line_edit.text()
		cut = max(text.rfind("+"), text.rfind("&"))
		head = text[:cut + 1] if cut >= 0 else ""
		if head.endswith("&"):
			head += " "
		return head + index.data()


class MappingPage(QWidget):
	"""Supported device, the remote's picture and its mapping list, as on the Mac 按键映射 page."""

	def __init__(self):
		super().__init__()
		self.setObjectName("page")
		self.path = daemon.DEFAULT_CONFIG_PATH
		self.rows = {}
		self.hidden = {}
		self.voice = dict(daemon.DEFAULT_VOICE)
		self.completion = QStringListModel(["none", "atvv:toggle", "atvv:hold", "cmd:"] + ALL_KEYS, self)
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(16)

		devices = card()
		devices.setFixedWidth(270)
		devices_layout = QVBoxLayout(devices)
		devices_layout.setContentsMargins(18, 18, 18, 16)
		devices_layout.setSpacing(10)
		devices_layout.addWidget(label("支持的设备", "secondary"))
		self.device = card("deviceActive")
		device_layout = QVBoxLayout(self.device)
		device_layout.setContentsMargins(14, 12, 14, 12)
		name_row = QHBoxLayout()
		self.device_dot = Dot(TERTIARY)
		name_row.addWidget(self.device_dot)
		device_name = label("Chromecast Voice Remote")
		device_name.setStyleSheet("font-weight: 700;")
		name_row.addWidget(device_name, 1)
		device_layout.addLayout(name_row)
		id_row = QHBoxLayout()
		id_row.addWidget(label("18D1 · 9450", "mono"))
		id_row.addStretch(1)
		self.device_state = label("未连接", "secondary")
		id_row.addWidget(self.device_state)
		device_layout.addLayout(id_row)
		devices_layout.addWidget(self.device)
		devices_layout.addStretch(1)
		devices_layout.addWidget(label("✓ 设置跟随型号，不绑定某一只遥控器", "good", wrap=True))
		layout.addWidget(devices)

		main = card()
		main_layout = QHBoxLayout(main)
		main_layout.setContentsMargins(22, 20, 22, 18)
		main_layout.setSpacing(22)
		picture = QVBoxLayout()
		self.remote = RemoteView()
		self.remote.clicked.connect(self.select)
		picture.addWidget(self.remote, 1)
		caption = label("15 个按键 · 14 个可映射", "caption")
		caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
		picture.addWidget(caption)
		main_layout.addLayout(picture)
		divider = QFrame()
		divider.setObjectName("vline")
		main_layout.addWidget(divider)
		right = QVBoxLayout()
		right.setSpacing(10)
		head = QHBoxLayout()
		head.addLayout(card_header("Chromecast Voice Remote", "点击遥控器上的按键或右侧菜单修改映射"), 1)
		head.addWidget(label("启用映射", "secondary"))
		self.enabled = ToggleSwitch()
		self.enabled.toggled.connect(self.mark_dirty)
		self.enabled.setToolTip("关闭后不接管遥控器按键，按键恢复系统默认行为（语音键不受影响）")
		head.addWidget(self.enabled)
		right.addLayout(head)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QFrame.Shape.NoFrame)
		self.list_widget = QWidget()
		self.list_layout = QVBoxLayout(self.list_widget)
		self.list_layout.setContentsMargins(0, 0, 6, 0)
		self.list_layout.setSpacing(6)
		scroll.setWidget(self.list_widget)
		right.addWidget(scroll, 1)
		footer = QHBoxLayout()
		self.status = label("", "caption")
		footer.addWidget(self.status, 1)
		reload_button = QPushButton("重新载入")
		reload_button.clicked.connect(self.load)
		reset_button = QPushButton("恢复默认")
		reset_button.setObjectName("link")
		reset_button.clicked.connect(self.reset)
		self.save_button = QPushButton("保存并应用")
		self.save_button.setObjectName("primary")
		self.save_button.clicked.connect(self.save)
		for b in (reset_button, reload_button, self.save_button):
			footer.addWidget(b)
		right.addLayout(footer)
		main_layout.addLayout(right, 1)
		layout.addWidget(main, 1)
		self.load()

	def fill(self, specs):
		self.hidden = {name: spec for name, spec in specs.items() if name not in PHYSICAL_BUTTONS}
		while self.list_layout.count():
			item = self.list_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.rows = {}
		for name in PHYSICAL_BUTTONS:
			row = MappingRow(name, specs.get(name), self.completion)
			row.selected.connect(self.select)
			row.changed.connect(self.mark_dirty)
			self.rows[name] = row
			self.list_layout.addWidget(row)
		self.list_layout.addStretch(1)
		self.select(None)

	def select(self, name):
		self.remote.selected = name
		self.remote.update()
		for row_name, row in self.rows.items():
			row.set_selected(row_name == name)
		if name in self.rows:
			self.list_widget.parentWidget().parentWidget().ensureWidgetVisible(self.rows[name])

	def mark_dirty(self, *_args):
		self.status.setText("有未保存的改动")
		self.status.setObjectName("warn")
		self.status.style().unpolish(self.status)
		self.status.style().polish(self.status)

	def set_status(self, text):
		self.status.setText(text)
		self.status.setObjectName("caption")
		self.status.style().unpolish(self.status)
		self.status.style().polish(self.status)

	def load(self):
		try:
			buttons, self.voice, general = read_config(self.path)
		except daemon.tomllib.TOMLDecodeError as e:
			QMessageBox.warning(self, "配置文件错误", str(e))
			return
		self.enabled.blockSignals(True)
		self.enabled.setChecked(bool(general.get("enabled", True)))
		self.enabled.blockSignals(False)
		self.fill(buttons)
		self.set_status(f"已载入 {self.path.replace(os.path.expanduser('~'), '~')}")

	def reset(self):
		self.fill(dict(daemon.DEFAULT_BUTTONS))
		self.mark_dirty()
		self.status.setText("已恢复默认（尚未保存）")

	def save(self):
		buttons = dict(self.hidden)
		for name, row in self.rows.items():
			if row.spec is None:
				continue
			try:
				daemon.Target(row.spec)
			except ValueError as e:
				QMessageBox.warning(self, "映射无效", f"{BUTTON_LABELS.get(name, name)}：{e}")
				return
			buttons[name] = row.spec
		# The audio page can change voice settings while this page stays open.
		self.voice = read_config(self.path)[1]
		write_config(self.path, buttons, self.voice, {"enabled": self.enabled.isChecked()})
		restart_service("vremoter-linux")
		self.set_status(f"已保存并重启映射服务（{time.strftime('%H:%M:%S')}）")

	def key_seen(self, name):
		self.remote.pressed(name)
		self.select(name)

	def set_connected(self, connected):
		self.device_dot.set_color(GREEN if connected else TERTIARY)
		self.device_state.setText("已连接" if connected else "未连接")
		self.device_state.setObjectName("good" if connected else "secondary")
		self.device_state.style().unpolish(self.device_state)
		self.device_state.style().polish(self.device_state)


# ── Test and log pages ─────────────────────────────────────────────────────────────────────────────────────────────────────


class TestPage(QWidget):
	"""Press every key (they light up on the picture), try both voice gestures, and make one recording."""

	def __init__(self):
		super().__init__()
		self.setObjectName("page")
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(16)

		picture_card = card()
		picture_card.setFixedWidth(270)
		picture_layout = QVBoxLayout(picture_card)
		picture_layout.setContentsMargins(18, 18, 18, 16)
		picture_layout.addWidget(label("逐个按遥控器上的键", "secondary"))
		self.remote = RemoteView(interactive=False)
		picture_layout.addWidget(self.remote, 1)
		self.progress = label("", "good")
		self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
		picture_layout.addWidget(self.progress)
		layout.addWidget(picture_card)

		right = QVBoxLayout()
		right.setSpacing(16)
		keys = card()
		keys_layout = QVBoxLayout(keys)
		keys_layout.setContentsMargins(22, 16, 22, 16)
		keys_layout.addLayout(card_header("1. 按键测试", "按到的键在左图上变绿；语音键通过 ATVVoice 识别"))
		self.last_key = StatusLine("最近按键")
		keys_layout.addWidget(self.last_key)
		reset = QPushButton("重新开始按键测试")
		reset.clicked.connect(self.reset_keys)
		keys_layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignRight)
		right.addWidget(keys)
		voice = card()
		voice_layout = QVBoxLayout(voice)
		voice_layout.setContentsMargins(22, 16, 22, 16)
		voice_layout.addLayout(card_header("2. 语音键测试", "短按一次开麦、再短按一次关；按住说话后松开（分界 0.55 秒）"))
		self.tap_row = StatusLine("短按开关")
		self.hold_row = StatusLine("按住说话")
		self.state_row = StatusLine("麦克风状态")
		for row in (self.tap_row, self.hold_row, self.state_row):
			voice_layout.addWidget(row)
		right.addWidget(voice)
		record = card()
		record_layout = QVBoxLayout(record)
		record_layout.setContentsMargins(22, 16, 22, 16)
		record_layout.addLayout(card_header("3. 录音试听", "到「音频」页录一段，峰值高于 −30 dBFS 即通过"))
		self.record_row = StatusLine("录到清晰的人声")
		record_layout.addWidget(self.record_row)
		right.addWidget(record)
		right.addStretch(1)
		layout.addLayout(right, 1)
		for row in (self.last_key, self.tap_row, self.hold_row, self.state_row, self.record_row):
			row.set("warn", "尚未测试")
		self.reset_keys()

	def reset_keys(self):
		self.remote.tested.clear()
		self.remote.update()
		self.update_progress()

	def update_progress(self):
		done = len(self.remote.tested)
		self.progress.setText(f"已测试 {done} / {len(REMOTE_HOTSPOTS)} 个键" + ("  ✓" if done == len(REMOTE_HOTSPOTS) else ""))

	def key_seen(self, name, target):
		if name in REMOTE_HOTSPOTS:
			self.remote.tested.add(name)
			self.remote.pressed(name)
			self.update_progress()
		self.last_key.set("good", f"{BUTTON_LABELS.get(name, name)} → {target}")

	def gesture_seen(self, kind, seconds):
		row = self.tap_row if kind == "tap" else self.hold_row
		row.set("good", f"最近一次 {seconds:.2f} 秒")
		self.key_seen("voice", "ATVVoice 语音")

	def mic_state(self, state):
		names = {"streaming": "正在收音", "connected": "已连接，未开麦", "opening": "正在开麦", "disconnected": "未连接", "unavailable": "服务未运行"}
		self.state_row.set("good" if state in ("streaming", "connected") else "warn", names.get(state, state))

	def recording_seen(self, peak_db):
		self.record_row.set("good" if peak_db > -30 else "bad", f"最近一段峰值 {peak_db:.1f} dBFS")


class LogPage(QWidget):

	def __init__(self):
		super().__init__()
		self.setObjectName("page")
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		box = card()
		box_layout = QVBoxLayout(box)
		box_layout.setContentsMargins(22, 16, 22, 16)
		head = QHBoxLayout()
		head.addLayout(card_header("服务日志", "journalctl --user-unit vremoter-linux --user-unit atvvoice"), 1)
		self.hide_noise = QCheckBox("隐藏刷屏信息")
		self.hide_noise.setToolTip("每个按键都会产生的 HttButtonRelease、AUDIO_SYNC 等")
		self.hide_noise.setChecked(True)
		clear = QPushButton("清空")
		head.addWidget(self.hide_noise)
		head.addWidget(clear)
		box_layout.addLayout(head)
		self.view = QPlainTextEdit()
		self.view.setReadOnly(True)
		self.view.setMaximumBlockCount(5000)
		clear.clicked.connect(self.view.clear)
		box_layout.addWidget(self.view, 1)
		layout.addWidget(box)

	def add(self, line):
		if self.hide_noise.isChecked() and re.search(r"HttButtonRelease\)$|AUDIO_SYNC|Sequence gap|PipeWire node ID|stream state", line):
			return
		self.view.appendPlainText(line)


# ── Main window ────────────────────────────────────────────────────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):

	def __init__(self):
		super().__init__()
		self.setWindowTitle("vRemoter 控制台")
		self.resize(1120, 920)
		self.setMinimumSize(980, 760)
		logo = asset("vRemoter-app-icon-v9.png")
		if logo:
			self.setWindowIcon(QIcon(logo))
		self.atvv = Atvv()
		self.recording = False
		self.checks = {}

		root = QWidget()
		root.setObjectName("root")
		outer = QVBoxLayout(root)
		outer.setContentsMargins(26, 22, 26, 20)
		outer.setSpacing(18)

		header = card("header")
		header.setFixedHeight(76)
		header_layout = QHBoxLayout(header)
		header_layout.setContentsMargins(14, 8, 22, 8)
		header_layout.setSpacing(14)
		logo_label = QLabel()
		if logo:
			pixmap = QPixmap(logo).scaled(104, 104, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
			pixmap.setDevicePixelRatio(2)
			logo_label.setPixmap(pixmap)
		header_layout.addWidget(logo_label)
		brand = QVBoxLayout()
		brand.setSpacing(0)
		brand.addWidget(label("vRemoter", "brand"))
		brand.addWidget(label("遥控器语音输入", "subtitle"))
		header_layout.addLayout(brand)
		header_layout.addSpacing(10)
		self.segment = Segmented(["音频", "按键映射", "测试", "日志"], self.show_page)
		header_layout.addWidget(self.segment)
		header_layout.addStretch(1)
		self.status_dot = Dot(TERTIARY, 12)
		self.status_text = label("正在检查", "secondary")
		self.status_text.setStyleSheet("font-size: 17px; font-weight: 700;")
		header_layout.addWidget(self.status_dot)
		header_layout.addWidget(self.status_text)
		outer.addWidget(header)

		self.test = TestPage()
		self.audio = AudioPage(self.atvv, self.test.recording_seen, self.recording_changed)
		self.mapping = MappingPage()
		self.log = LogPage()
		self.stack = QStackedWidget()
		audio_scroll = QScrollArea()  # the audio page is the tallest; it scrolls rather than squeezing its cards together
		audio_scroll.setWidgetResizable(True)
		audio_scroll.setFrameShape(QFrame.Shape.NoFrame)
		audio_scroll.setWidget(self.audio)
		for page in (audio_scroll, self.mapping, self.test, self.log):
			self.stack.addWidget(page)
		outer.addWidget(self.stack, 1)
		self.setCentralWidget(root)

		if not self.atvv.bus.connect("", daemon.ATVV_PATH, daemon.ATVV_INTERFACE, "MicStateChanged", self.on_mic_state):
			print("warning: cannot subscribe to ATVVoice MicStateChanged", file=sys.stderr)
		self.journal = QProcess(self)
		self.journal.readyReadStandardOutput.connect(self.read_journal)
		# --user-unit rather than --user -u: without a persistent journal (no /var/log/journal, e.g. some Ubuntu 24.04
		# installs) user-unit logs live only in the system journal and `journalctl --user` finds nothing.
		self.journal.start("journalctl", ["--user-unit", "vremoter-linux", "--user-unit", "atvvoice", "-f", "-n", "0", "-o", "cat"])
		self.journal_buffer = ""

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.refresh)
		self.timer.start(2000)
		self.refresh()
		self.on_mic_state(self.atvv.state())

	def show_page(self, index):
		self.stack.setCurrentIndex(index)

	def refresh(self):
		address = self.atvv.device_address()
		connected = bt_connected(address)
		state = self.atvv.state()
		active = run("systemctl", "--user", "is-active", "vremoter-linux")
		source = run("pactl", "get-default-source")
		self.checks = {
			"bt": ("good", f"已连接 · {address}") if connected else ("warn", "未连接，按遥控器任意键唤醒"),
			"atvv": restarting("atvvoice", ("good", {
				"streaming": "正在收音",
				"connected": "已就绪"
			}.get(state, state)) if state in ("streaming", "connected") else ("bad", state)),
			"map": restarting("vremoter-linux", ("good", "运行中") if active == "active" else ("bad", active or "未运行")),
			"mic": ("good", "遥控器麦克风") if source == SOURCE_NAME else ("warn", source or "未知"),
		}
		self.audio.set_checks(self.checks)
		self.mapping.set_connected(connected)
		self.update_status()

	def update_status(self):
		states = [state for state, _ in self.checks.values()]
		if self.recording:
			color, text = AMBER, "录音中"
		elif "bad" in states:
			color, text = RED, "需要处理"
		elif "busy" in states:
			color, text = AMBER, "服务重启中"
		elif self.checks.get("bt", ("warn", ""))[0] != "good":
			color, text = AMBER, "等待遥控器"
		elif "warn" in states:
			color, text = AMBER, "需要留意"
		else:
			color, text = GREEN, "正在运行"
		self.status_dot.set_color(color)
		self.status_text.setText(text)
		self.status_text.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {color};")

	def recording_changed(self, on):
		self.recording = on
		self.update_status()

	@pyqtSlot(str)
	def on_mic_state(self, state):
		self.test.mic_state(state)
		self.audio.mic_state(state)

	def read_journal(self):
		self.journal_buffer += bytes(self.journal.readAllStandardOutput()).decode(errors="replace")
		*lines, self.journal_buffer = self.journal_buffer.split("\n")
		for line in lines:
			line = ANSI.sub("", line)
			self.log.add(line)
			if match := re.match(r"\[key\] (\S+) DOWN -> (.*)", line):
				self.test.key_seen(match.group(1), match.group(2))
				self.mapping.key_seen(match.group(1))
			elif match := re.search(r"HttButtonRelease\) after ([\d.]+)(µs|ms|s) (tap|hold)", line):
				seconds = float(match.group(1)) / {"µs": 1e6, "ms": 1000, "s": 1}[match.group(2)]
				self.test.gesture_seen(match.group(3), seconds)
				self.mapping.key_seen("voice")

	def closeEvent(self, event):
		if self.audio.manual:
			self.atvv.call("MicClose")
		if self.audio.capture:
			self.audio.capture.finished.disconnect()
		for process in (self.journal, self.audio.capture, self.audio.player):
			if process:
				process.kill()
				process.waitForFinished(1000)
		super().closeEvent(event)


def dark_palette():
	palette = QPalette()
	for role, color in ((QPalette.ColorRole.Window, SURFACE), (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Base, BLACK), (QPalette.ColorRole.AlternateBase, SURFACE2),
						(QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE2), (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, "#2D6B48"),
						(QPalette.ColorRole.HighlightedText, TEXT), (QPalette.ColorRole.ToolTipBase, SURFACE2), (QPalette.ColorRole.ToolTipText,
																													TEXT), (QPalette.ColorRole.PlaceholderText, TERTIARY)):
		palette.setColor(role, QColor(color))
	for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
		palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TERTIARY))
	return palette


def main():
	app = QApplication(sys.argv)
	app.setApplicationName("vRemoter")
	app.setDesktopFileName("vremoter-gui")
	app.setStyle("Fusion")
	app.setPalette(dark_palette())
	app.setStyleSheet(STYLE)
	window = MainWindow()
	window.show()
	return app.exec()


if __name__ == "__main__":
	sys.exit(main())
