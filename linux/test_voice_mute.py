import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import vremoter_linux as daemon


class OutputMuteTests(unittest.TestCase):

	def setUp(self):
		self.output = daemon.OutputMute()
		self.commands = patch.object(self.output, "pactl").start()
		self.addCleanup(patch.stopall)

	def test_mute_once_and_restore_original_device(self):
		self.commands.side_effect = ["speakers", "Mute: no", "", ""]
		self.output.start()
		self.output.start()
		self.output.restore()
		self.output.restore()
		self.assertEqual(
			self.commands.call_args_list,
			[call("get-default-sink"), call("get-sink-mute", "speakers"),
				call("set-sink-mute", "speakers", "1"),
				call("set-sink-mute", "speakers", "0")])

	def test_already_muted_output_stays_muted(self):
		self.commands.side_effect = ["speakers", "Mute: yes"]
		self.output.start()
		self.output.restore()
		self.assertEqual(self.commands.call_count, 2)

	def test_read_failure_does_not_change_output(self):
		for result in (FileNotFoundError(), subprocess.TimeoutExpired("pactl", 2), "unexpected"):
			with self.subTest(result=result):
				self.commands.reset_mock()
				self.commands.side_effect = ["speakers", result]
				self.output.start()
				self.output.restore()
				self.assertIsNone(self.output.sink)
				self.assertEqual(self.commands.call_count, 2)

	def test_mute_timeout_still_restores(self):
		self.commands.side_effect = ["speakers", "Mute: no", subprocess.TimeoutExpired("pactl", 2), ""]
		self.output.start()
		self.output.restore()
		self.commands.assert_called_with("set-sink-mute", "speakers", "0")
		self.assertIsNone(self.output.sink)

	def test_restore_failure_can_be_retried_without_losing_device(self):
		self.output.sink = "speakers"
		self.commands.side_effect = [subprocess.CalledProcessError(1, "pactl"), ""]
		self.output.restore()
		self.assertEqual(self.output.sink, "speakers")
		self.output.start()
		self.output.restore()
		self.assertIsNone(self.output.sink)
		self.assertEqual(self.commands.call_args_list, [call("set-sink-mute", "speakers", "0")] * 2)

	def test_pactl_uses_explicit_arguments_timeout_and_fixed_locale(self):
		with patch.object(daemon.subprocess, "run", return_value=MagicMock(stdout="Mute: no\n")) as run:
			self.assertEqual(daemon.OutputMute().pactl("get-sink-mute", "speakers"), "Mute: no")
			self.assertEqual(run.call_args.args[0], ["pactl", "get-sink-mute", "speakers"])
			self.assertTrue(run.call_args.kwargs["check"])
			self.assertEqual(run.call_args.kwargs["timeout"], 2)
			self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")


class VoiceTests(unittest.TestCase):

	def setUp(self):
		self.bus = MagicMock()
		self.voice = daemon.AtvVoice(self.bus, daemon.DEFAULT_VOICE)
		self.voice.output = MagicMock()
		self.hooks = patch.object(daemon, "run_command").start()
		self.addCleanup(patch.stopall)

	def test_stream_handoff_stays_muted_until_stop(self):
		for state in ("streaming", "streaming", "opening", "streaming"):
			self.voice.on_state(state)
		self.voice.output.start.assert_called_once()
		self.voice.output.restore.assert_not_called()
		self.voice.on_state("connected")
		self.voice.output.restore.assert_called_once()
		self.assertFalse(self.voice.streaming)
		self.assertEqual(self.hooks.call_count, 2)

	def test_disabled_setting_keeps_output_unchanged(self):
		self.voice.mute_output = False
		self.voice.on_state("streaming")
		self.voice.output.start.assert_not_called()
		self.assertTrue(self.voice.streaming)
		self.hooks.assert_called_once()

	def test_disconnect_and_daemon_exit_restore(self):
		for stop in (lambda: self.voice.on_state("disconnected"), lambda: self.voice.on_owner("")):
			with self.subTest(stop=stop):
				self.voice.output.reset_mock()
				self.voice.on_state("streaming")
				stop()
				self.voice.output.restore.assert_called_once()
				self.assertFalse(self.voice.streaming)

	def test_startup_queries_state_and_ignores_reply_from_lost_owner(self):
		self.voice.on_owner(":1.42")
		method = self.bus.get_object.return_value.get_dbus_method.return_value
		reply = method.call_args.kwargs["reply_handler"]
		reply("streaming")
		self.voice.output.start.assert_called_once()
		self.voice.on_owner("")
		reply("streaming")
		self.assertFalse(self.voice.streaming)
		self.voice.output.start.assert_called_once()
		self.assertEqual(self.bus.add_signal_receiver.call_args.kwargs["bus_name"], self.voice.bus_name)

	def test_main_restores_on_loop_error(self):
		with patch.object(daemon, "load_config", return_value=({}, daemon.DEFAULT_VOICE, {
			"enabled": False
		})), patch.object(daemon, "AtvVoice") as voice, patch.object(daemon.GLib, "MainLoop") as loop, patch.object(daemon, "add_signal_handler"), patch.object(
			daemon.dbus, "SessionBus"), patch("sys.argv", ["vremoter"]):
			loop.return_value.run.side_effect = RuntimeError("loop failed")
			with self.assertRaises(RuntimeError):
				daemon.main()
			voice.return_value.output.restore.assert_called_once()


if __name__ == "__main__":
	unittest.main()
