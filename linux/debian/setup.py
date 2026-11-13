#!/usr/bin/python3
"""Initialize per-user settings and migrate files from the old ./install.sh installation."""

import os
from pathlib import Path
import re
import subprocess
import time


def initialize(home, config, data):
	migrated = False
	defaults = (data / "config.example.toml").read_text()
	config_path = config / "vremoter/config.toml"
	config_path.parent.mkdir(parents=True, exist_ok=True)
	try:
		with config_path.open("x") as output:
			output.write(defaults)
	except FileExistsError:
		pass

	# Remove only exact copies of our old installer files, keeping a backup and leaving custom files alone.
	for old, template in ((home / ".config/systemd/user/vremoter-linux.service", "legacy-vremoter-linux.service"), (home / ".local/share/applications/vremoter-gui.desktop",
																													"legacy-vremoter-gui.desktop")):
		if old.is_file() and old.read_bytes() == (data / template).read_bytes():
			backup = old.with_name(old.name + ".pre-deb")
			if not backup.exists():
				old.rename(backup)
			else:
				old.unlink()
			migrated = True

	# The GUI's existing audio overrides must use the bundled binary and the console's instance name.
	override = home / ".config/systemd/user/atvvoice.service.d/override.conf"
	if override.is_file():
		original = override.read_text()
		lines = []
		for line in original.splitlines(keepends=True):
			match = re.match(r"ExecStart=(\S+)(.*)", line.rstrip("\n"))
			if match and match[1] in ("/usr/bin/atvvoice", str(home / ".local/bin/atvvoice")):
				args = match[2]
				if not re.search(r"(?:^|\s)(?:--name|-n)(?:[=\s]|$)", args):
					args += " --name chromecast-remote"
				line = "/usr/bin/atvvoice" + args
				line = "ExecStart=" + line + "\n"
			lines.append(line)
		updated = "".join(lines)
		if updated != original:
			backup = override.with_name(override.name + ".pre-deb")
			if not backup.exists():
				backup.write_text(original)
			temporary = override.with_name(override.name + ".tmp")
			temporary.write_text(updated)
			temporary.replace(override)
			migrated = True
	return migrated


def main():
	home = Path.home()
	migrated = initialize(home, Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")), Path("/usr/share/vremoter"))
	subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
	# A graceful stop plus a short gap lets BlueZ release ATVVoice's exclusive notify handles after an upgrade.
	if migrated:
		subprocess.run(["systemctl", "--user", "stop", "vremoter-linux.service", "atvvoice.service"], check=True)
		time.sleep(2)
	subprocess.run(["systemctl", "--user", "start", "atvvoice.service", "vremoter-linux.service"], check=True)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
