import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("setup", Path(__file__).with_name("setup.py"))
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):

	def setUp(self):
		self.temporary = tempfile.TemporaryDirectory()
		self.addCleanup(self.temporary.cleanup)
		self.home = Path(self.temporary.name)
		self.config = self.home / ".config"
		self.data = self.home / "data"
		self.data.mkdir()
		linux = Path(__file__).resolve().parents[1]
		for source, target in (("config.example.toml", "config.example.toml"), ("vremoter-linux.service", "legacy-vremoter-linux.service"), ("vremoter-gui.desktop",
																																				"legacy-vremoter-gui.desktop")):
			(self.data / target).write_bytes((linux / source).read_bytes())

	def write(self, path, text):
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(text)
		return path

	def initialize(self):
		return setup.initialize(self.home, self.config, self.data)

	def test_first_run_and_custom_settings_survive_repeated_setup(self):
		self.assertFalse(self.initialize())
		config = self.config / "vremoter/config.toml"
		self.assertEqual(config.read_bytes(), (self.data / "config.example.toml").read_bytes())
		config.write_text('[buttons]\nyoutube = "KEY_F9"\n')
		self.assertFalse(self.initialize())
		self.assertEqual(config.read_text(), '[buttons]\nyoutube = "KEY_F9"\n')

	def test_only_known_legacy_files_migrate_with_backups(self):
		unit = self.write(self.config / "systemd/user/vremoter-linux.service", (self.data / "legacy-vremoter-linux.service").read_text())
		desktop = self.write(self.home / ".local/share/applications/vremoter-gui.desktop", "custom desktop file\n")
		self.assertTrue(self.initialize())
		self.assertFalse(unit.exists())
		self.assertEqual(unit.with_name(unit.name + ".pre-deb").read_bytes(), (self.data / "legacy-vremoter-linux.service").read_bytes())
		self.assertEqual(desktop.read_text(), "custom desktop file\n")
		self.assertFalse(self.initialize())

	def test_audio_override_migration_preserves_device_and_filters(self):
		original = f"[Service]\nExecStart=\nExecStart={self.home}/.local/bin/atvvoice --device AA:BB:CC:DD:EE:FF --gain 7 --highpass 90 --fade-in 100\n"
		override = self.write(self.config / "systemd/user/atvvoice.service.d/override.conf", original)
		self.assertTrue(self.initialize())
		self.assertEqual(override.read_text(), original.replace(f"{self.home}/.local/bin/atvvoice", "/usr/bin/atvvoice").rstrip("\n") + " --name chromecast-remote\n")
		self.assertEqual(override.with_name("override.conf.pre-deb").read_text(), original)
		self.assertFalse(self.initialize())

	def test_custom_binary_and_explicit_instance_are_preserved(self):
		override = self.write(self.config / "systemd/user/atvvoice.service.d/override.conf", "[Service]\nExecStart=/opt/custom/atvvoice --gain 3\n")
		self.assertFalse(self.initialize())
		self.assertIn("/opt/custom/atvvoice", override.read_text())
		override.write_text("[Service]\nExecStart=/usr/bin/atvvoice --name=other-remote --gain 3\n")
		self.assertFalse(self.initialize())
		self.assertNotIn("chromecast-remote", override.read_text())

	def test_services_restart_only_when_migration_changes_files(self):
		for migrated in (False, True):
			with self.subTest(migrated=migrated), patch.object(setup, "initialize",
																return_value=migrated), patch.object(setup.subprocess, "run") as run, patch.object(setup.time, "sleep") as sleep:
				self.assertEqual(setup.main(), 0)
				commands = [call.args[0] for call in run.call_args_list]
				self.assertEqual(commands[0], ["systemctl", "--user", "daemon-reload"])
				self.assertEqual(commands[-1], ["systemctl", "--user", "start", "atvvoice.service", "vremoter-linux.service"])
				self.assertEqual(len(commands), 3 if migrated else 2)
				self.assertEqual(sleep.call_count, int(migrated))


if __name__ == "__main__":
	unittest.main()
