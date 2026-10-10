# vRemoter for Linux

Linux port of vRemoter's Chromecast Voice Remote (VID `0x18D1` / PID `0x9450`) support. The macOS app's audio stack (CoreAudio driver, mic mixing) and Doubao integration have no Linux counterpart; this port splits the remaining work in two:

| #   | Part                   | Provided by                                                         | macOS equivalent                                             |
| --- | ---------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------ |
| 1   | Remote microphone      | [ATVVoice (vRemoter fork)](https://github.com/zhanglongqi/ATVVoice) | `BLEBridge` + `ATVV/` + `AudioPipe` + `vRemoteDriver.driver` |
| 2   | Button remapping       | `vremoter_linux.py`                                                 | `ChromecastRemoteHIDBridge` + `RemoteMappingSupport`         |
| 3   | Voice start/stop hooks | `vremoter_linux.py` (ATVVoice D-Bus signal)                         | `X6SessionCoordinator` triggering Doubao                     |

ATVVoice is a BlueZ/PipeWire daemon speaking the same ATVV protocol as `Sources/vRemote/ATVV/`. It exposes the remote microphone as a PipeWire source (`atvvoice-chromecast-remote`) and publishes its state on the session D-Bus as `org.atvvoice.chromecast-remote`.

## Setup

1. For the complete Debian package (console, ATVVoice, services and permissions), see [the Linux release guide](debian/RELEASE.md). Install with `pkexec apt install ./vremoter_1.1.1-1_amd64.deb`, then log out and back in.
2. To build that package from this checkout and its sibling `ATVVoice` checkout, run `bash linux/build-deb.sh` from the `vRemoter` repository. Requires Rust/Cargo, `libpipewire-0.3-dev`, `libdbus-1-dev`, `pkg-config`, `libclang-dev`, `dpkg-dev` and `binutils`; outputs go to `dist/linux/` with SHA-256 checksums and source revision information. `ATVVOICE_SOURCE` can select another ATVVoice checkout. The build system's library versions determine the package's minimum runtime requirements.
3. Validate a built release without installing it: `python3 linux/debian/check-package.py dist/linux/vremoter_1.1.1-1_amd64.deb` (requires the runtime Python modules and `desktop-file-utils`). Run setup migration checks with `python3 -m unittest discover -s linux/debian`.

### Source installation

1. Pair the remote: hold **Back + Home** until the LED pulses, then pair from `bluetoothctl` (`scan on`, `pair <addr>`, `trust <addr>`, `connect <addr>`). The remote only advertises in pairing mode.
2. Install ATVVoice from the [vRemoter-compatible release `v0.2.0-vremote.1`](https://github.com/zhanglongqi/ATVVoice/releases/tag/v0.2.0-vremote.1) (x86_64 `.deb` or standalone binary; Ubuntu 24.04+ / glibc 2.39+). This fork includes Chromecast hold-to-talk handling, per-stream `--highpass` / `--fade-in` options, and Bluetooth adapter recovery used by this Linux integration. Use this release for the setup below, pin it to the remote and enable it:

   ```bash
   systemctl --user edit atvvoice   # [Service] / ExecStart= / ExecStart=/usr/bin/atvvoice --device <addr> --name chromecast-remote
   systemctl --user enable --now atvvoice
   ```

3. Install this daemon (needs `python3-evdev`, `python3-dbus`, `python3-gi`, `pulseaudio-utils` for `pactl`, and membership in the `input` group):

   ```bash
   ./install.sh
   ```

   It installs to `~/.local/lib/vremoter/`, copies `config.example.toml` to `~/.config/vremoter/config.toml` if none exists, and enables the `vremoter-linux` user service.

## Buttons

The daemon grabs the remote's evdev node exclusively and re-emits mapped actions through a uinput device named `vRemoter Chromecast Remote`. Without it the kernel's default HID mapping applies, which turns several TV keys into harmful desktop keys:

| #   | Button  | HID usage | Kernel default              | vRemoter default     |
| --- | ------- | --------- | --------------------------- | -------------------- |
| 1   | Power   | `0x019E`  | `KEY_SCREENLOCK`            | none                 |
| 2   | YouTube | `0x0077`  | `KEY_CAMERA_ACCESS_DISABLE` | none                 |
| 3   | Netflix | `0x0078`  | `KEY_CAMERA_ACCESS_TOGGLE`  | none                 |
| 4   | Input   | `0x0089`  | `KEY_TV`                    | none                 |
| 5   | Home    | `0x0223`  | `KEY_HOMEPAGE`              | `KEY_LEFTMETA+KEY_D` |
| 6   | Back    | `0x0224`  | `KEY_BACK`                  | `KEY_ESC`            |
| 7   | Select  | `0x0041`  | `KEY_SELECT`                | `KEY_ENTER`          |

Arrows, mute and volume keep their usual keys. Each button can be set to a key, a key combo, a shell command (`cmd:...`) or an ATVVoice action (`atvv:toggle` / `atvv:open` / `atvv:close`); see `config.example.toml`. Restart the service after editing: `systemctl --user restart vremoter-linux`.

## Voice key

The voice key never reaches evdev: it travels over ATVV and is handled by ATVVoice. `[voice] on_start` / `on_stop` in the config run commands whenever ATVVoice's state enters or leaves `streaming`, which is where a voice input method can be triggered.

While the remote microphone is streaming, vRemoter automatically mutes the default audio output before running `on_start`. It restores the same output device when recording stops,
the remote disconnects, ATVVoice exits, or vRemoter exits normally (including SIGTERM/SIGINT). An output already muted is left muted. This also works when button remapping is
disabled. It uses `pactl` through PipeWire's PulseAudio compatibility service; failures are logged without stopping microphone capture.

The output device is captured at the start of each recording; switching outputs during recording does not mute the new device. SIGKILL or a crash that bypasses cleanup can leave
the output muted; unmute it in the desktop audio settings.

The audio page's **录音时静音输出** checkbox enables or disables this behavior and saves immediately. The equivalent config setting is `[voice] mute_output = true` (the default).

Run the voice mute and GUI configuration checks with `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s linux -p 'test_voice_mute*.py'`.

## Logs

```bash
journalctl --user-unit vremoter-linux -f
journalctl --user-unit atvvoice -f
```
