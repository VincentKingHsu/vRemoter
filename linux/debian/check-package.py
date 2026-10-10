#!/usr/bin/python3
"""Check a built .deb without installing it or touching the running desktop services."""

import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def check(package):
	with tempfile.TemporaryDirectory() as directory:
		root = Path(directory)
		subprocess.run(["dpkg-deb", "-x", str(package), directory], check=True)
		subprocess.run(["dpkg-deb", "-e", str(package), str(root / "DEBIAN")], check=True)
		subprocess.run(["md5sum", "--quiet", "-c", "DEBIAN/md5sums"], cwd=root, check=True)
		for command in ("atvvoice", "vremoter-gui", "vremoter-pair", "vremoter-setup"):
			assert os.access(root / "usr/bin" / command, os.X_OK), command
		for unit in ("atvvoice", "vremoter-linux"):
			link = root / f"usr/lib/systemd/user/default.target.wants/{unit}.service"
			assert link.resolve().is_file(), unit
		for script in ("postinst", "prerm", "postrm"):
			subprocess.run(["sh", "-n", str(root / "DEBIAN" / script)], check=True)
		subprocess.run(["desktop-file-validate", str(root / "usr/share/applications/vremoter-gui.desktop"), str(root / "etc/xdg/autostart/vremoter-autostart.desktop")], check=True)
		subprocess.run(["udevadm", "verify", str(root / "usr/lib/udev/rules.d/70-vremoter.rules")], check=True)
		help_text = subprocess.run([str(root / "usr/bin/atvvoice"), "--help"], capture_output=True, text=True, check=True).stdout
		for flag in ("--name", "--gain", "--highpass", "--fade-in"):
			assert flag in help_text, flag
		# The installed command has no .py extension, so supply the loader explicitly.
		spec = importlib.util.spec_from_loader("setup", SourceFileLoader("setup", str(root / "usr/bin/vremoter-setup")))
		setup = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(setup)
		home = root / "home"
		config = home / ".config"
		assert not setup.initialize(home, config, root / "usr/share/vremoter")
		assert not setup.initialize(home, config, root / "usr/share/vremoter")
		environment = dict(os.environ,
							HOME=str(home),
							XDG_CONFIG_HOME=str(config),
							XDG_DATA_HOME=str(home / ".local/share"),
							XDG_RUNTIME_DIR=str(root / "runtime"),
							DBUS_SESSION_BUS_ADDRESS=f"unix:path={root}/missing-bus",
							QT_QPA_PLATFORM="offscreen",
							PYTHONDONTWRITEBYTECODE="1")
		(root / "runtime").mkdir(mode=0o700)
		subprocess.run(["/usr/bin/python3", str(root / "usr/lib/vremoter/vremoter_linux.py"), "--check"], env=environment, check=True, capture_output=True, text=True)
		code = """
import sys
sys.path.insert(0, sys.argv[1])
import vremoter_gui as gui
app = gui.QApplication([])
window = gui.MainWindow()
assert not window.windowIcon().isNull()
window.show()
gui.QTimer.singleShot(300, window.close)
gui.QTimer.singleShot(400, app.quit)
raise SystemExit(app.exec())
"""
		subprocess.run(["/usr/bin/python3", "-c", code, str(root / "usr/lib/vremoter")], env=environment, check=True, timeout=20)
	print("Package payload, permissions, launchers, defaults, ATVVoice CLI and offscreen Qt startup: OK")


if __name__ == "__main__":
	check(Path(sys.argv[1]).resolve())
