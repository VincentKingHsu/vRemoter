import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QCheckBox, QWidget
import vremoter_gui as gui


class MuteSettingTests(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.app = QApplication.instance() or QApplication([])

	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.addCleanup(self.temp.cleanup)
		self.path = str(Path(self.temp.name) / "config.toml")
		self.config = patch.object(gui.daemon, "DEFAULT_CONFIG_PATH", self.path)
		self.config.start()
		self.addCleanup(self.config.stop)
		self.page = gui.AudioPage.__new__(gui.AudioPage)
		QWidget.__init__(self.page)
		self.page.mute_output = QCheckBox()

	def test_toggle_round_trip_preserves_other_settings(self):
		buttons = {"netflix": ["atvv:hold", "KEY_F9"]}
		voice = {**gui.daemon.DEFAULT_VOICE, "on_start": "echo start"}
		gui.write_config(self.path, buttons, voice, {"enabled": False})
		with patch.object(gui, "restart_service") as restart:
			for enabled in (False, True):
				self.page.save_output_mute(enabled)
				_, saved_voice, saved_general = gui.read_config(self.path)
				self.assertIs(saved_voice["mute_output"], enabled)
				self.assertEqual(saved_voice["on_start"], "echo start")
				self.assertFalse(saved_general["enabled"])
				self.assertEqual(gui.read_config(self.path)[0]["netflix"], buttons["netflix"])
				self.assertIs(gui.daemon.load_config(self.path)[1]["mute_output"], enabled)
			self.assertEqual(restart.call_count, 2)
			restart.assert_called_with("vremoter-linux")

	def test_save_failure_reverts_checkbox_and_does_not_restart(self):
		with patch.object(gui, "write_config", side_effect=OSError("read only")), patch.object(gui, "restart_service") as restart, patch.object(gui.QMessageBox,
																																				"warning") as warning:
			self.page.save_output_mute(False)
			self.assertTrue(self.page.mute_output.isChecked())
			restart.assert_not_called()
			warning.assert_called_once()

	def test_invalid_boolean_is_rejected_by_daemon(self):
		Path(self.path).write_text('[voice]\nmute_output = "false"\n')
		with self.assertRaisesRegex(ValueError, "must be a boolean"):
			gui.daemon.load_config(self.path)

	def test_mapping_save_preserves_new_audio_setting(self):
		gui.write_config(self.path, {}, {**gui.daemon.DEFAULT_VOICE, "mute_output": False}, {"enabled": True})
		page = gui.MappingPage.__new__(gui.MappingPage)
		QWidget.__init__(page)
		page.path = self.path
		page.hidden = {}
		page.rows = {}
		page.voice = dict(gui.daemon.DEFAULT_VOICE)
		page.enabled = QCheckBox()
		page.enabled.setChecked(True)
		page.set_status = MagicMock()
		with patch.object(gui, "restart_service"):
			page.save()
		self.assertFalse(gui.read_config(self.path)[1]["mute_output"])


if __name__ == "__main__":
	unittest.main()
