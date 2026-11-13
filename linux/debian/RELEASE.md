# vRemoter Linux 1.1.1-1

1. Includes the Linux console, button mapping daemon, vRemoter-compatible ATVVoice 0.2.0, two systemd user services, application-menu launcher, pairing helper, images and configuration defaults.
2. Microphone defaults: instance `chromecast-remote`, gain 12 dB, high-pass 80 Hz, fade-in 200 ms. Button mappings use `config.example.toml`; existing user mappings and audio overrides are preserved.
3. The active local desktop session receives access to Chromecast input devices and `/dev/uinput`. No membership in the broad `input` group is required. Access to `uinput` allows applications in that session to generate keyboard events.
4. Services start at login. Desktop autostart and the console launcher initialize missing user configuration and migrate exact copies of the old installer files, saving `.pre-deb` backups. Recognized ATVVoice overrides retain device and audio options while using `/usr/bin/atvvoice` and the console's instance name.

## Install

1. Install the `.deb` with your package manager so dependencies are resolved: `pkexec apt install ./vremoter_1.1.1-1_amd64.deb`.
2. Log out and log back in, then open **vRemoter** from the application menu. This applies session permissions and activates the packaged services. The console can also be opened with `vremoter-gui`.
3. Pair a new remote: hold **Back + Home** until its LED blinks, then run `vremoter-pair`. Bluetooth addresses and bonding keys are specific to each machine and are not included in the package.
4. Customize buttons and audio processing in the console. Logs: `journalctl --user-unit vremoter-linux --user-unit atvvoice -f`.

## Compatibility and removal

1. This release is an amd64 build produced and smoke-tested on Ubuntu 26.04, with a minimum glibc requirement of 2.39. The package declares the library versions required by its bundled binary; installation on Ubuntu 24.04 or another compatible distribution still needs validation. Do not force installation if dependencies cannot be satisfied. A build on another supported Ubuntu/Debian system can use the same packaging script.
2. Python, Qt, BlueZ and PipeWire are package-manager dependencies rather than bundled copies. Installing on a machine without them requires access to its configured package repositories. A working PipeWire desktop session and Bluetooth adapter are required.
3. The package replaces a separately installed `atvvoice` Debian package because it supplies the same executable and service. Old user-installed binaries remain on disk, but recognized service overrides migrate to the bundled binary. Custom service files, custom executable locations and explicit custom instance names are preserved and may require manual adjustment.
4. Remove with `pkexec apt remove vremoter`. Existing user settings, recordings and `.pre-deb` backups remain available for reinstalling. To disable services for one user, run `systemctl --user mask --now vremoter-linux.service atvvoice.service`.
5. The package has been extracted and smoke-tested without changing the developer machine's installed services. A fresh-machine installation and a hardware recording test remain to be performed.
