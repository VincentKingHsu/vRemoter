#!/usr/bin/env python3
"""vRemoter for Linux - test, mapping and recording console for the Chromecast Voice Remote.

A front end over the two background services:

1. vremoter-linux (vremoter_linux.py) grabs the remote's keys; this window follows its journal to see presses, and edits its
   config file for mappings.
2. atvvoice exposes the remote microphone as a PipeWire source; this window follows its D-Bus state and journal for voice-key
   gestures, records from the source and can change its gain.
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
from PyQt6.QtCore import QProcess, QRectF, QStringListModel, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow,
								QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vremoter_linux as daemon  # noqa: E402

SOURCE_NAME = "atvvoice-chromecast-remote"
SAMPLE_RATE = 16000
ATVV_NAME = "chromecast-remote"
ATVV_SERVICE = f"org.atvvoice.{ATVV_NAME}"
ATVV_OVERRIDE = os.path.expanduser("~/.config/systemd/user/atvvoice.service.d/override.conf")
RECORDINGS_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "vremoter", "recordings")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Button names (as in vremoter_linux.BUTTONS) -> label, laid out roughly like the physical remote.
BUTTON_LABELS = {
	"power": "电源",
	"input": "信源",
	"up": "上",
	"left": "左",
	"select": "确认",
	"right": "右",
	"down": "下",
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
REMOTE_LAYOUT = [
	["power", None, "input"],
	[None, "up", None],
	["left", "select", "right"],
	[None, "down", None],
	["back", "home", "voice"],
	["youtube", "mute", "netflix"],
	["volume_down", None, "volume_up"],
]
# The 15 physical keys in layout order. The HID descriptor also declares play_pause, search and usage_79, which no key on
# this remote sends; the mapping table hides them but keeps their configured values.
PHYSICAL_BUTTONS = [name for row in REMOTE_LAYOUT for name in row if name]
# Mapping drop-down: (group, [(action, description), ...]). Every evdev key name is appended after these, and the edit box
# completes key names token by token, so anything the daemon accepts can be picked or typed.
MAPPING_GROUPS = [
	("常用", [("none", "不映射（屏蔽此键）")]),
	("导航", [
		("KEY_UP", "上"),
		("KEY_DOWN", "下"),
		("KEY_LEFT", "左"),
		("KEY_RIGHT", "右"),
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
		("KEY_MUTE", "静音"),
		("KEY_VOLUMEUP", "音量+"),
		("KEY_VOLUMEDOWN", "音量-"),
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
		("KEY_HOMEPAGE", "主页"),
		("KEY_LEFTCTRL+KEY_T", "Ctrl+T 新标签页"),
		("KEY_LEFTCTRL+KEY_W", "Ctrl+W 关闭标签页"),
		("KEY_LEFTCTRL+KEY_TAB", "Ctrl+Tab 下一个标签页"),
		("KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_TAB", "Ctrl+Shift+Tab 上一个标签页"),
		("KEY_LEFTCTRL+KEY_EQUAL", "Ctrl+= 放大"),
		("KEY_LEFTCTRL+KEY_MINUS", "Ctrl+- 缩小"),
		("KEY_LEFTCTRL+KEY_0", "Ctrl+0 原始大小"),
	]),
	("桌面 / 系统", [
		("KEY_LEFTMETA", "Meta（打开开始菜单）"),
		("KEY_LEFTMETA+KEY_D", "Meta+D 显示桌面"),
		("KEY_LEFTALT+KEY_TAB", "Alt+Tab 切换窗口"),
		("KEY_LEFTALT+KEY_F4", "Alt+F4 关闭窗口"),
		("KEY_LEFTMETA+KEY_UP", "Meta+↑ 最大化"),
		("KEY_LEFTCTRL+KEY_LEFTMETA+KEY_LEFT", "上一个虚拟桌面（KDE）"),
		("KEY_LEFTCTRL+KEY_LEFTMETA+KEY_RIGHT", "下一个虚拟桌面（KDE）"),
		("KEY_LEFTMETA+KEY_L", "Meta+L 锁屏"),
		("KEY_SCREENLOCK", "锁屏键"),
		("KEY_SYSRQ", "PrintScreen 截图"),
		("KEY_BRIGHTNESSUP", "亮度+"),
		("KEY_BRIGHTNESSDOWN", "亮度-"),
		("KEY_SLEEP", "睡眠"),
		("KEY_POWER", "电源键（弹出关机对话框）"),
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
		("KEY_F9", "F9（fcitx5 vocotype 按住说话）"),
		("KEY_RIGHTALT+KEY_0", "右 Alt+0（Vokie）"),
		("atvv:hold & KEY_RIGHTALT+KEY_0", "按住：开麦克风 + 右 Alt+0（Vokie）"),
		("atvv:hold & KEY_F9", "按住：开麦克风 + F9（vocotype）"),
	]),
	("命令", [
		("cmd:xdg-open https://www.youtube.com", "打开 YouTube"),
		("cmd:xdg-open https://www.netflix.com", "打开 Netflix"),
		("cmd:loginctl lock-session", "锁屏"),
	]),
]
# Every key the daemon's uinput device can emit, minus range markers.
ALL_KEYS = sorted(n for n in daemon.ecodes.ecodes if n.startswith(("KEY_", "BTN_")) and n not in ("KEY_MAX", "KEY_CNT", "KEY_RESERVED", "KEY_MIN_INTERESTING", "BTN_MISC"))

OK, PENDING, BAD = "✅", "⬜", "❌"


def run(*cmd, timeout=3):
	"""Run a short command and return its stdout ('' on failure)."""
	try:
		return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
	except (OSError, subprocess.TimeoutExpired):
		return ""


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


def read_config(path):
	"""Raw button specs and voice settings from the daemon config, defaults filled in."""
	buttons = dict(daemon.DEFAULT_BUTTONS)
	voice = dict(daemon.DEFAULT_VOICE)
	if os.path.exists(path):
		with open(path, "rb") as f:
			data = daemon.tomllib.load(f)
		buttons.update(data.get("buttons", {}))
		voice.update(data.get("voice", {}))
	return buttons, voice


def write_config(path, buttons, voice):
	lines = ["# vRemoter for Linux configuration (written by vremoter_gui.py; see config.example.toml for the syntax).", "", "[buttons]"]
	for name, spec in buttons.items():
		value = "[" + ", ".join(toml_string(p) for p in spec) + "]" if isinstance(spec, list) else toml_string(spec)
		lines.append(f"{name} = {value}")
	lines += ["", "[voice]"] + [f"{k} = {toml_string(str(v))}" for k, v in voice.items()]
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


class StatusRow(QWidget):

	def __init__(self, title, action_text=None):
		super().__init__()
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		self.icon = QLabel(PENDING)
		self.title = QLabel(title)
		self.detail = QLabel("")
		self.detail.setStyleSheet("color: gray")
		layout.addWidget(self.icon)
		layout.addWidget(self.title)
		layout.addWidget(self.detail, 1)
		self.button = None
		if action_text:
			self.button = QPushButton(action_text)
			layout.addWidget(self.button)

	def set(self, ok, detail):
		self.icon.setText(OK if ok else BAD)
		self.detail.setText(detail)
		if self.button:
			self.button.setVisible(not ok)


class WizardTab(QWidget):
	"""Step-by-step checks: services, every button, voice gestures and a recording."""

	def __init__(self, atvv):
		super().__init__()
		self.atvv = atvv
		self.pressed = set()
		layout = QVBoxLayout(self)

		checks = QGroupBox("1. 连接与服务")
		checks_layout = QVBoxLayout(checks)
		self.bt_row = StatusRow("遥控器蓝牙连接", "唤醒提示")
		self.atvv_row = StatusRow("ATVVoice 麦克风服务", "重启服务")
		self.map_row = StatusRow("按键映射服务", "重启服务")
		self.mic_row = StatusRow("默认麦克风是遥控器", "设为默认")
		for row in (self.bt_row, self.atvv_row, self.map_row, self.mic_row):
			checks_layout.addWidget(row)
		self.bt_row.button.clicked.connect(lambda: QMessageBox.information(self, "唤醒遥控器", "按遥控器任意键唤醒它，它会自动回连。\n如果长时间连不上，按住「返回 + 主页」进入配对模式后重新配对。"))
		self.atvv_row.button.clicked.connect(lambda: restart_service("atvvoice"))
		self.map_row.button.clicked.connect(lambda: restart_service("vremoter-linux"))
		self.mic_row.button.clicked.connect(lambda: run("pactl", "set-default-source", SOURCE_NAME))
		layout.addWidget(checks)

		keys = QGroupBox("2. 按键测试：逐个按遥控器上的键，按到的键会变绿")
		keys_layout = QHBoxLayout(keys)
		grid = QGridLayout()
		self.key_labels = {}
		for r, row in enumerate(REMOTE_LAYOUT):
			for c, name in enumerate(row):
				if name is None:
					continue
				label = QLabel(BUTTON_LABELS[name])
				label.setAlignment(Qt.AlignmentFlag.AlignCenter)
				label.setMinimumSize(84, 34)
				self.key_labels[name] = label
				self.paint_key(name, False)
				grid.addWidget(label, r, c)
		keys_layout.addLayout(grid)
		side = QVBoxLayout()
		self.key_progress = QLabel()
		self.last_key = QLabel("最近按键：—")
		self.last_key.setWordWrap(True)
		reset = QPushButton("重新开始按键测试")
		reset.clicked.connect(self.reset_keys)
		side.addWidget(self.key_progress)
		side.addWidget(self.last_key)
		side.addStretch(1)
		side.addWidget(reset)
		keys_layout.addLayout(side, 1)
		layout.addWidget(keys)

		voice = QGroupBox("3. 语音键测试：短按一次开麦、再短按一次关；按住说话后松开")
		voice_layout = QVBoxLayout(voice)
		self.tap_row = StatusRow("短按开关（按下松开 < 0.55 秒）")
		self.hold_row = StatusRow("按住说话（按住 ≥ 0.55 秒）")
		self.voice_state = QLabel("麦克风状态：—")
		for w in (self.tap_row, self.hold_row, self.voice_state):
			voice_layout.addWidget(w)
		layout.addWidget(voice)

		record = QGroupBox("4. 录音试听：到「录音」页录一段，峰值高于 -30 dBFS 即通过")
		record_layout = QVBoxLayout(record)
		self.record_row = StatusRow("录到清晰的人声")
		record_layout.addWidget(self.record_row)
		layout.addWidget(record)
		layout.addStretch(1)
		self.reset_keys()

	def paint_key(self, name, pressed):
		color = "#2e7d32; color: white" if pressed else "#e0e0e0; color: black"
		self.key_labels[name].setStyleSheet(f"background: {color}; border-radius: 6px; padding: 4px")

	def reset_keys(self):
		self.pressed.clear()
		for name in self.key_labels:
			self.paint_key(name, False)
		self.update_key_progress()

	def update_key_progress(self):
		self.key_progress.setText(f"已测试 {len(self.pressed)} / {len(self.key_labels)} 个键" + (" ✅" if len(self.pressed) == len(self.key_labels) else ""))

	def key_seen(self, name, target):
		if name in self.key_labels:
			self.pressed.add(name)
			self.paint_key(name, True)
			self.update_key_progress()
		self.last_key.setText(f"最近按键：{BUTTON_LABELS.get(name, name)} → {target}")

	def gesture_seen(self, kind, seconds):
		row = self.tap_row if kind == "tap" else self.hold_row
		row.set(True, f"最近一次 {seconds:.2f} 秒")
		self.key_seen("voice", "ATVV 语音")

	def mic_state(self, state):
		self.voice_state.setText(f"麦克风状态：{state}")

	def recording_seen(self, peak_db):
		self.record_row.set(peak_db > -30, f"最近一段峰值 {peak_db:.1f} dBFS")

	def refresh(self):
		address = self.atvv.device_address()
		info = run("bluetoothctl", "info", address) if address else ""
		connected = "Connected: yes" in info
		self.bt_row.set(connected, address or "ATVVoice 未报告设备地址")
		state = self.atvv.state()
		self.atvv_row.set(state not in ("unavailable", "disconnected"), state)
		active = run("systemctl", "--user", "is-active", "vremoter-linux")
		self.map_row.set(active == "active", active)
		source = run("pactl", "get-default-source")
		self.mic_row.set(source == SOURCE_NAME, source)


def header_item(text):
	item = QStandardItem(f"── {text} ──")
	item.setFlags(Qt.ItemFlag.NoItemFlags)
	return item


def mapping_model():
	"""Drop-down entries for the mapping editor: grouped presets (with descriptions as tooltips), then every evdev key."""
	model = QStandardItemModel()
	for group, actions in MAPPING_GROUPS:
		model.appendRow(header_item(group))
		for action, description in actions:
			item = QStandardItem(action)
			item.setToolTip(description)
			model.appendRow(item)
	model.appendRow(header_item(f"全部按键（{len(ALL_KEYS)} 个）"))
	for name in ALL_KEYS:
		model.appendRow(QStandardItem(name))
	return model


class TokenCompleter(QCompleter):
	"""Completes only the token after the last '+' or '&', so combos like KEY_LEFTCTRL+KEY_T can be typed piece by piece."""

	def __init__(self, model, line_edit):
		super().__init__(model, line_edit)
		self.line_edit = line_edit  # widget() is the combo box when the line edit belongs to one
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


class MappingTab(QWidget):
	"""Edit the daemon's button mapping and restart it."""

	def __init__(self):
		super().__init__()
		self.path = daemon.DEFAULT_CONFIG_PATH
		layout = QVBoxLayout(self)
		hint = QLabel("每个键可以是：none、按键（如 KEY_ENTER）、组合键（KEY_RIGHTALT+KEY_0）、cmd:命令、atvv:toggle / atvv:hold；"
						"多个动作用 & 连接，例如 atvv:hold & KEY_F9（按住时开遥控器麦克风并按住 F9）。"
						"下拉框按类别列出常用动作，末尾是全部 evdev 按键；也可以直接输入，会按 + / & 后面的部分自动补全（如输入 vol）。")
		hint.setWordWrap(True)
		layout.addWidget(hint)
		self.table = QTableWidget(0, 3)
		self.table.setHorizontalHeaderLabels(["遥控器按键", "映射到", "HID 用途"])
		self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
		self.table.verticalHeader().setVisible(False)
		layout.addWidget(self.table, 1)
		buttons = QHBoxLayout()
		reload_button = QPushButton("重新载入")
		reset_button = QPushButton("恢复默认")
		save_button = QPushButton("保存并应用")
		save_button.setDefault(True)
		reload_button.clicked.connect(self.load)
		reset_button.clicked.connect(self.reset)
		save_button.clicked.connect(self.save)
		self.status = QLabel("")
		buttons.addWidget(self.status, 1)
		for b in (reload_button, reset_button, save_button):
			buttons.addWidget(b)
		layout.addLayout(buttons)
		self.voice = dict(daemon.DEFAULT_VOICE)
		self.model = mapping_model()
		self.completion = QStringListModel(["none", "atvv:toggle", "atvv:hold", "cmd:"] + ALL_KEYS, self)
		self.load()

	def fill(self, specs):
		usages = {name: usage for usage, name in daemon.BUTTONS.items()}
		self.hidden = {name: spec for name, spec in specs.items() if name not in PHYSICAL_BUTTONS}
		self.table.setRowCount(0)
		for name in PHYSICAL_BUTTONS:
			row = self.table.rowCount()
			self.table.insertRow(row)
			item = QTableWidgetItem(f"{BUTTON_LABELS.get(name, name)}  ({name})")
			item.setData(Qt.ItemDataRole.UserRole, name)
			item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
			self.table.setItem(row, 0, item)
			if name not in specs:
				# The voice key never reaches the HID device: ATVVoice handles it over the ATVV GATT service.
				note = QTableWidgetItem("由 ATVVoice 处理：短按开/关遥控器麦克风，按住说话（不可映射）")
				note.setFlags(Qt.ItemFlag.ItemIsEnabled)
				self.table.setItem(row, 1, note)
				self.table.setItem(row, 2, QTableWidgetItem("ATVV"))
				self.table.item(row, 2).setFlags(Qt.ItemFlag.ItemIsEnabled)
				continue
			spec = specs[name]
			combo = QComboBox()
			combo.setEditable(True)
			combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
			combo.setModel(self.model)
			combo.setMaxVisibleItems(25)
			combo.lineEdit().setCompleter(TokenCompleter(self.completion, combo.lineEdit()))  # not combo.setCompleter: that selects rows of the combo model
			text = spec_to_text(spec)
			combo.setCurrentIndex(combo.findText(text))  # so the popup opens on it; -1 if not listed
			combo.setCurrentText(text)
			self.table.setCellWidget(row, 1, combo)
			usage = QTableWidgetItem(f"0x{usages[name] & 0xFFFF:04X}" if name in usages else "")
			usage.setFlags(usage.flags() & ~Qt.ItemFlag.ItemIsEditable)
			self.table.setItem(row, 2, usage)
		self.table.resizeColumnToContents(0)

	def load(self):
		try:
			buttons, self.voice = read_config(self.path)
		except daemon.tomllib.TOMLDecodeError as e:
			QMessageBox.warning(self, "配置文件错误", str(e))
			return
		self.fill(buttons)
		self.status.setText(f"已载入 {self.path}")

	def reset(self):
		self.fill(dict(daemon.DEFAULT_BUTTONS))
		self.status.setText("已恢复默认（尚未保存）")

	def save(self):
		buttons = dict(self.hidden)
		for row in range(self.table.rowCount()):
			name = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
			if self.table.cellWidget(row, 1) is None:
				continue
			spec = text_to_spec(self.table.cellWidget(row, 1).currentText())
			try:
				daemon.Target(spec)
			except ValueError as e:
				QMessageBox.warning(self, "映射无效", f"{BUTTON_LABELS.get(name, name)}：{e}")
				return
			buttons[name] = spec
		write_config(self.path, buttons, self.voice)
		restart_service("vremoter-linux")
		self.status.setText(f"已保存并重启映射服务（{time.strftime('%H:%M:%S')}）")


class LevelMeter(QWidget):
	"""Scrolling level history (newest on the right) next to a peak meter with peak hold and a clip lamp, in dBFS."""

	FLOOR = -60.0
	BLOCK = SAMPLE_RATE // 20  # 50 ms per history column
	HISTORY = 15  # seconds kept on screen
	HOLD = 1.5  # seconds the peak-hold marker stays before falling
	GRID = (-6, -12, -20, -30, -40, -50)
	METER_WIDTH = 26
	LABEL_WIDTH = 34

	def __init__(self):
		super().__init__()
		self.setMinimumHeight(190)
		self.history = collections.deque(maxlen=self.HISTORY * SAMPLE_RATE // self.BLOCK)  # (rms_db, peak_db, recording)
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
			self.rms_db = max(self.FLOOR, dbfs(math.sqrt(sum(s * s for s in block) / len(block))))
			self.peak_db = max(self.FLOOR, dbfs(peak))
			if self.live:
				self.history.append((self.rms_db, self.peak_db, recording))
			now = time.monotonic()
			if self.peak_db >= self.hold_db or now - self.hold_since > self.HOLD:
				self.hold_db, self.hold_since = self.peak_db, now
			if peak >= 32760:
				self.clip_until = now + self.HOLD
			self.update()

	def y_of(self, db, top, height):
		return top + height * min(1.0, max(0.0, db / self.FLOOR))

	@staticmethod
	def zone_color(db):
		return QColor("#e5484d") if db > -3 else QColor("#f5a524") if db > -12 else QColor("#30a46c")

	def paintEvent(self, _event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
		w, h = self.width(), self.height()
		top, height = 6, h - 22
		graph_left, graph_right = self.LABEL_WIDTH, w - self.METER_WIDTH - 10
		p.fillRect(self.rect(), QColor("#16181d"))

		# Grid and dB labels.
		p.setFont(QFont("monospace", 7))
		for db in self.GRID:
			y = int(self.y_of(db, top, height))
			p.setPen(QPen(QColor("#3a3f4b"), 1, Qt.PenStyle.DotLine))
			p.drawLine(graph_left, y, graph_right, y)
			p.setPen(QColor("#8b93a1"))
			p.drawText(0, y - 6, self.LABEL_WIDTH - 4, 12, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(db))

		# History: one column per block, RMS filled, peak as a thin cap; recorded stretches shaded behind.
		columns = self.history.maxlen
		col_w = (graph_right - graph_left) / columns
		bottom = top + height
		start = columns - len(self.history)
		for i, entry in enumerate(self.history):
			x = graph_left + (start + i) * col_w
			if entry is None:
				p.fillRect(QRectF(x + col_w / 2 - 0.5, top, 1, height), QColor("#5b6270"))
				continue
			rms_db, peak_db, recording = entry
			if recording:
				p.fillRect(QRectF(x, top, col_w + 0.5, height), QColor(229, 72, 77, 40))
			y_rms = self.y_of(rms_db, top, height)
			p.fillRect(QRectF(x, y_rms, col_w + 0.5, bottom - y_rms), self.zone_color(rms_db))
			y_peak = self.y_of(peak_db, top, height)
			p.fillRect(QRectF(x, y_peak, col_w + 0.5, 1.5), self.zone_color(peak_db).lighter(140))

		# Time axis.
		p.setPen(QColor("#8b93a1"))
		p.drawText(graph_left, bottom + 2, 120, 14, Qt.AlignmentFlag.AlignLeft, f"-{self.HISTORY} 秒")
		p.drawText(graph_right - 60, bottom + 2, 60, 14, Qt.AlignmentFlag.AlignRight, "现在")
		if not self.live:
			p.drawText(graph_left + 6, top, 200, 14, Qt.AlignmentFlag.AlignLeft, "未开麦，历史已暂停")

		# Peak meter: gradient zones dimmed, lit up to the current peak, RMS as a darker inner bar, hold marker.
		mx = w - self.METER_WIDTH - 4
		zones = ((self.FLOOR, -12), (-12, -3), (-3, 0))
		for lo, hi in zones:
			y_hi, y_lo = self.y_of(hi, top, height), self.y_of(lo, top, height)
			color = self.zone_color(hi - 0.1)
			p.fillRect(QRectF(mx, y_hi, self.METER_WIDTH, y_lo - y_hi), color.darker(400))
			lit_top = max(y_hi, self.y_of(self.peak_db, top, height))
			if lit_top < y_lo:
				p.fillRect(QRectF(mx, lit_top, self.METER_WIDTH, y_lo - lit_top), color)
		y_rms = self.y_of(self.rms_db, top, height)
		p.fillRect(QRectF(mx + self.METER_WIDTH / 3, y_rms, self.METER_WIDTH / 3, bottom - y_rms), QColor(255, 255, 255, 90))
		if self.hold_db > self.FLOOR:
			p.fillRect(QRectF(mx, self.y_of(self.hold_db, top, height) - 1, self.METER_WIDTH, 2), QColor("#ffffff"))
		clipped = time.monotonic() < self.clip_until
		p.fillRect(QRectF(mx, bottom + 4, self.METER_WIDTH, 10), QColor("#e5484d") if clipped else QColor("#3a1f22"))
		p.end()


class RecordingTab(QWidget):
	"""Level meter, manual / automatic recording from the remote mic, playback and ATVVoice gain."""

	def __init__(self, atvv, on_take):
		super().__init__()
		self.atvv = atvv
		self.on_take = on_take
		self.capture = None
		self.recording = False
		self.manual = False
		self.samples = array.array("h")
		self.pending = b""
		self.player = None
		self.capture_args = pw_record_args()
		os.makedirs(RECORDINGS_DIR, exist_ok=True)
		layout = QVBoxLayout(self)

		meter_box = QGroupBox(f"电平（{SOURCE_NAME}）")
		meter_layout = QVBoxLayout(meter_box)
		self.meter = LevelMeter()
		self.meter_text = QLabel("未开麦时为静音")
		meter_layout.addWidget(self.meter)
		meter_layout.addWidget(self.meter_text)
		layout.addWidget(meter_box)

		controls = QHBoxLayout()
		self.record_button = QPushButton("开麦并录音")
		self.record_button.setCheckable(True)
		self.record_button.toggled.connect(self.toggle_manual)
		self.auto = QCheckBox("语音键 / atvv:hold 开麦时自动录音")
		self.auto.setChecked(True)
		controls.addWidget(self.record_button)
		controls.addWidget(self.auto, 1)
		layout.addLayout(controls)

		gain_box = QGroupBox("ATVVoice 增益（改动后会重启 ATVVoice）")
		gain_layout = QHBoxLayout(gain_box)
		self.gain = QSpinBox()
		self.gain.setRange(0, 40)
		self.gain.setSuffix(" dB")
		self.gain.setValue(self.current_gain())
		apply_gain = QPushButton("应用")
		apply_gain.clicked.connect(self.apply_gain)
		gain_layout.addWidget(QLabel("增益"))
		gain_layout.addWidget(self.gain)
		gain_layout.addWidget(apply_gain)
		gain_layout.addStretch(1)
		layout.addWidget(gain_box)

		takes_box = QGroupBox(f"录音（保存在 {RECORDINGS_DIR}）")
		takes_layout = QVBoxLayout(takes_box)
		self.takes = QListWidget()
		self.takes.itemDoubleClicked.connect(self.play)
		row = QHBoxLayout()
		play = QPushButton("播放所选")
		stop = QPushButton("停止播放")
		play.clicked.connect(lambda: self.play(self.takes.currentItem()))
		stop.clicked.connect(self.stop_playback)
		row.addStretch(1)
		row.addWidget(play)
		row.addWidget(stop)
		takes_layout.addWidget(self.takes)
		takes_layout.addLayout(row)
		layout.addWidget(takes_box, 1)
		self.load_takes()
		self.start_capture()

	# Capture runs continuously for the meter; samples are kept only while recording.
	def start_capture(self):
		if SOURCE_NAME not in run("pactl", "list", "short", "sources"):
			# pw-record would silently fall back to another mic; wait for ATVVoice to publish the source.
			self.meter.reset()
			self.meter_text.setText("遥控器麦克风不存在（遥控器未连接或 ATVVoice 未运行），稍后自动重试")
			QTimer.singleShot(2000, self.start_capture)
			return
		self.capture = QProcess(self)
		self.capture.readyReadStandardOutput.connect(self.read_capture)
		self.capture.finished.connect(self.capture_finished)
		self.capture.start("pw-record", self.capture_args)

	def capture_finished(self, code, _status):
		if code != 0:
			error = bytes(self.capture.readAllStandardError()).decode(errors="replace").strip().splitlines()
			self.meter.reset()
			self.meter_text.setText(f"pw-record 退出（{code}）：{error[0] if error else '无输出'}，稍后自动重试")
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
		self.meter_text.setText(f"平均 {dbfs(rms):6.1f} dBFS   峰值 {dbfs(peak):6.1f} dBFS" + ("   ● 录音中" if self.recording else ""))

	def toggle_manual(self, on):
		self.manual = on
		self.record_button.setText("停止录音并关麦" if on else "开麦并录音")
		if on:
			error = self.atvv.call("MicOpen")
			if error:
				QMessageBox.warning(self, "开麦失败", error)
			self.begin()
		else:
			self.atvv.call("MicClose")
			self.end()

	def mic_state(self, state):
		self.meter.set_live(state == "streaming")
		if self.manual or not self.auto.isChecked():
			return
		if state == "streaming":
			self.begin()
		elif state in ("connected", "disconnected"):
			self.end()

	def begin(self):
		if not self.recording:
			self.samples = array.array("h")
			self.recording = True

	def end(self):
		if not self.recording:
			return
		self.recording = False
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
		text = f"{time.strftime('%m-%d %H:%M:%S', when)}  ·  {len(samples) / SAMPLE_RATE:.1f} 秒  ·  峰值 {peak:.1f} dBFS  ·  平均 {rms:.1f} dBFS"
		if clipped:
			text += f"  ·  ⚠ 削波 {clipped} 点（增益偏高）"
		item = QListWidgetItem(text)
		item.setData(Qt.ItemDataRole.UserRole, path)
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

	def current_gain(self):
		match = re.search(r"(?:-g|--gain)[ =](\d+)", self.atvv_command())
		return int(match.group(1)) if match else 20  # ATVVoice's own default

	def apply_gain(self):
		command = self.atvv_command()
		if not command:
			QMessageBox.warning(self, "无法修改增益", "读不到 atvvoice 服务的启动命令（systemctl --user show atvvoice）")
			return
		command = re.sub(r"\s(?:-g|--gain)[ =]\d+", "", command)
		# A drop-in leaves the installed unit alone; the empty ExecStart= clears the unit's own line first.
		os.makedirs(os.path.dirname(ATVV_OVERRIDE), exist_ok=True)
		with open(ATVV_OVERRIDE, "w") as f:
			f.write(f"[Service]\nExecStart=\nExecStart={command} --gain {self.gain.value()}\n")
		run("systemctl", "--user", "daemon-reload")
		restart_service("atvvoice")


class LogTab(QWidget):

	def __init__(self):
		super().__init__()
		layout = QVBoxLayout(self)
		self.hide_noise = QCheckBox("隐藏刷屏信息（每个按键都会产生的 HttButtonRelease、AUDIO_SYNC 等）")
		self.hide_noise.setChecked(True)
		self.view = QPlainTextEdit()
		self.view.setReadOnly(True)
		self.view.setMaximumBlockCount(5000)
		self.view.setFont(QFont("monospace"))
		clear = QPushButton("清空")
		clear.clicked.connect(self.view.clear)
		top = QHBoxLayout()
		top.addWidget(self.hide_noise, 1)
		top.addWidget(clear)
		layout.addLayout(top)
		layout.addWidget(self.view, 1)

	def add(self, line):
		if self.hide_noise.isChecked() and re.search(r"HttButtonRelease\)$|AUDIO_SYNC|Sequence gap|PipeWire node ID|stream state", line):
			return
		self.view.appendPlainText(line)


def restart_service(unit):
	# Stop, wait, start: an immediate restart of atvvoice can race BlueZ releasing its exclusive notify handles.
	subprocess.Popen(["sh", "-c", f"systemctl --user stop {unit}; sleep 2; systemctl --user start {unit}"], start_new_session=True)


class MainWindow(QMainWindow):

	def __init__(self):
		super().__init__()
		self.setWindowTitle("vRemoter 遥控器控制台")
		self.resize(980, 760)
		self.atvv = Atvv()
		tabs = QTabWidget()
		self.wizard = WizardTab(self.atvv)
		self.mapping = MappingTab()
		self.recording = RecordingTab(self.atvv, self.wizard.recording_seen)
		self.log = LogTab()
		tabs.addTab(self.wizard, "测试向导")
		tabs.addTab(self.mapping, "按键映射")
		tabs.addTab(self.recording, "录音")
		tabs.addTab(self.log, "日志")
		self.setCentralWidget(tabs)

		if not self.atvv.bus.connect("", daemon.ATVV_PATH, daemon.ATVV_INTERFACE, "MicStateChanged", self.on_mic_state):
			print("warning: cannot subscribe to ATVVoice MicStateChanged", file=sys.stderr)
		self.journal = QProcess(self)
		self.journal.readyReadStandardOutput.connect(self.read_journal)
		# --user-unit rather than --user -u: without a persistent journal (no /var/log/journal, e.g. some Ubuntu 24.04
		# installs) user-unit logs live only in the system journal and `journalctl --user` finds nothing.
		self.journal.start("journalctl", ["--user-unit", "vremoter-linux", "--user-unit", "atvvoice", "-f", "-n", "0", "-o", "cat"])
		self.journal_buffer = ""

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.wizard.refresh)
		self.timer.start(2000)
		self.wizard.refresh()
		self.on_mic_state(self.atvv.state())

	@pyqtSlot(str)
	def on_mic_state(self, state):
		self.wizard.mic_state(state)
		self.recording.mic_state(state)

	def read_journal(self):
		self.journal_buffer += bytes(self.journal.readAllStandardOutput()).decode(errors="replace")
		*lines, self.journal_buffer = self.journal_buffer.split("\n")
		for line in lines:
			line = ANSI.sub("", line)
			self.log.add(line)
			if match := re.match(r"\[key\] (\S+) DOWN -> (.*)", line):
				self.wizard.key_seen(match.group(1), match.group(2))
			elif match := re.search(r"HttButtonRelease\) after ([\d.]+)(ms|s) (tap|hold)", line):
				seconds = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
				self.wizard.gesture_seen(match.group(3), seconds)

	def closeEvent(self, event):
		if self.recording.manual:
			self.atvv.call("MicClose")
		if self.recording.capture:
			self.recording.capture.finished.disconnect()
		for process in (self.journal, self.recording.capture, self.recording.player):
			if process:
				process.kill()
				process.waitForFinished(1000)
		super().closeEvent(event)


def main():
	app = QApplication(sys.argv)
	app.setApplicationName("vRemoter")
	window = MainWindow()
	window.show()
	return app.exec()


if __name__ == "__main__":
	sys.exit(main())
