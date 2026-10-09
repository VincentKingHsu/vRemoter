#!/usr/bin/env bash
# Install vRemoter for Linux as a systemd user service. Requires ATVVoice for the microphone (see README.md).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

if ! python3 -c 'import evdev, dbus, gi, PyQt6.QtDBus' 2>/dev/null; then
	echo "Missing Python modules. On Debian/Ubuntu: sudo apt install python3-evdev python3-dbus python3-gi python3-pyqt6" >&2
	exit 1
fi
if ! grep -qw input <<<"$(id -nG)"; then
	echo "warning: $(id -un) is not in the 'input' group; the daemon cannot read the remote or create uinput devices." >&2
fi

install -Dm755 "$here/vremoter_linux.py" "$HOME/.local/lib/vremoter/vremoter_linux.py"
install -Dm755 "$here/vremoter_gui.py" "$HOME/.local/lib/vremoter/vremoter_gui.py"
install -Dm644 "$here/vremoter-gui.desktop" "$HOME/.local/share/applications/vremoter-gui.desktop"
install -Dm644 "$here/../Resources/RemoteImages/chromecast-voice-remote.png" "$HOME/.local/lib/vremoter/assets/chromecast-voice-remote.png"
install -Dm644 "$here/../Design/vRemoter-Logo-v1/vRemoter-app-icon-v9.png" "$HOME/.local/lib/vremoter/assets/vRemoter-app-icon-v9.png"
install -Dm644 "$here/vremoter-linux.service" "$HOME/.config/systemd/user/vremoter-linux.service"
if [ ! -e "$HOME/.config/vremoter/config.toml" ]; then
	install -Dm644 "$here/config.example.toml" "$HOME/.config/vremoter/config.toml"
fi

python3 "$HOME/.local/lib/vremoter/vremoter_linux.py" --check
systemctl --user daemon-reload
systemctl --user enable --now vremoter-linux.service
systemctl --user restart vremoter-linux.service
echo "Installed. Logs: journalctl --user-unit vremoter-linux -f"
