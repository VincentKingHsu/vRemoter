# vRemoter for Linux

Linux port of vRemoter's Chromecast Voice Remote (VID `0x18D1` / PID `0x9450`) support. The macOS app's audio stack (CoreAudio driver, mic mixing) and Doubao integration have no Linux counterpart; this port splits the remaining work in two:

| #   | Part                   | Provided by                                 | macOS equivalent                                             |
| --- | ---------------------- | ------------------------------------------- | ------------------------------------------------------------ |
| 1   | Remote microphone      | [ATVVoice](https://github.com/b0o/ATVVoice) | `BLEBridge` + `ATVV/` + `AudioPipe` + `vRemoteDriver.driver` |
| 2   | Button remapping       | `vremoter_linux.py`                         | `ChromecastRemoteHIDBridge` + `RemoteMappingSupport`         |
| 3   | Voice start/stop hooks | `vremoter_linux.py` (ATVVoice D-Bus signal) | `X6SessionCoordinator` triggering Doubao                     |

ATVVoice is a BlueZ/PipeWire daemon speaking the same ATVV protocol as `Sources/vRemote/ATVV/`. It exposes the remote microphone as a PipeWire source (`atvvoice-chromecast-remote`) and publishes its state on the session D-Bus as `org.atvvoice.chromecast-remote`.

## Setup

1. Pair the remote: hold **Back + Home** until the LED pulses, then pair from `bluetoothctl` (`scan on`, `pair <addr>`, `trust <addr>`, `connect <addr>`). The remote only advertises in pairing mode.
2. Install ATVVoice from its [releases](https://github.com/b0o/ATVVoice/releases) (`.deb` / `.rpm`), pin it to the remote and enable it:

   ```bash
   systemctl --user edit atvvoice   # [Service] / ExecStart= / ExecStart=/usr/bin/atvvoice --device <addr>
   systemctl --user enable --now atvvoice
   ```

3. Install this daemon (needs `python3-evdev`, `python3-dbus`, `python3-gi`, and membership in the `input` group):

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

## Logs

```bash
journalctl --user-unit vremoter-linux -f
journalctl --user-unit atvvoice -f
```
