import AppKit

/// Minimal foreground control console for hardware diagnosis.
/// It intentionally exposes routing and live levels before any visual polish.
final class DebugWindowController: NSWindowController {
    var onStopMicrophone: (() -> Void)?
    var onRestartApp: (() -> Void)?
    var onMacInputEnabledChanged: ((Bool) -> Void)?
    var onRemoteInputEnabledChanged: ((Bool) -> Void)?
    var onOpenAccessibility: (() -> Void)?

    private let statusLabel = NSTextField(labelWithString: "状态 · 启动中")
    private let connectionLabel = NSTextField(labelWithString: "连接 · --")
    private let accessibilityLabel = NSTextField(labelWithString: "辅助功能拦截 · --")
    private let doubaoInputLabel = NSTextField(labelWithString: "豆包实际输入 · --")
    private let mappingLabel = NSTextField(labelWithString: "按键映射 · X6 语音键 → Option")
    private let macLevel = NSLevelIndicator()
    private let remoteLevel = NSLevelIndicator()
    private var lastMacLevelDB = -120.0
    private var lastRemoteLevelDB = -120.0
    private let macCheckbox = NSButton(checkboxWithTitle: "MacBook Air 内置麦克风 · 参与混音", target: nil, action: nil)
    private let remoteCheckbox = NSButton(checkboxWithTitle: "X6 遥控器麦克风 · 参与混音", target: nil, action: nil)

    init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 430),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "vRemote 控制台"
        window.center()
        window.isReleasedWhenClosed = false
        super.init(window: window)
        buildUI()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func show() {
        guard let window else { return }
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func update(
        status: String,
        hidConnected: Bool,
        bleConnected: Bool,
        accessibilityAvailable: Bool,
        remoteStreaming: Bool,
        macInputEnabled: Bool,
        remoteInputEnabled: Bool,
        doubaoIsRecording: Bool,
        doubaoInput: String,
        macLevelDB: Double? = nil,
        remoteLevelDB: Double? = nil
    ) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if let macLevelDB { self.lastMacLevelDB = macLevelDB }
            if let remoteLevelDB { self.lastRemoteLevelDB = remoteLevelDB }
            self.statusLabel.stringValue = "状态 · \(status)"
            self.connectionLabel.stringValue =
                "连接 · HID \(hidConnected ? "已连接" : "未连接") ｜ " +
                "X6 音频 \(bleConnected ? "已连接" : "未连接") ｜ " +
                "流 \(remoteStreaming ? "传输中" : "未启动")"
            self.accessibilityLabel.stringValue =
                "辅助功能拦截 · \(accessibilityAvailable ? "已授权" : "未授权（搜索拦截不可用）")"
            self.macCheckbox.state = macInputEnabled ? .on : .off
            self.remoteCheckbox.state = remoteInputEnabled ? .on : .off
            if doubaoIsRecording {
                let correct = doubaoInput.contains("vRemoteDr 2ch")
                self.doubaoInputLabel.stringValue = correct
                    ? "豆包实际输入 · vRemoteDr 2ch"
                    : "豆包实际输入 · \(doubaoInput)（应选择 vRemoteDr 2ch）"
                self.doubaoInputLabel.textColor = correct ? .systemGreen : .systemRed
            } else {
                self.doubaoInputLabel.stringValue = "豆包实际输入 · 当前未录音"
                self.doubaoInputLabel.textColor = .secondaryLabelColor
            }
            self.macLevel.doubleValue = Self.normalizedLevel(self.lastMacLevelDB)
            self.remoteLevel.doubleValue = Self.normalizedLevel(self.lastRemoteLevelDB)
        }
    }

    func updateMacLevel(_ db: Double) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.lastMacLevelDB = db
            self.macLevel.doubleValue = Self.normalizedLevel(db)
        }
    }

    func updateRemoteLevel(_ db: Double) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.lastRemoteLevelDB = db
            self.remoteLevel.doubleValue = Self.normalizedLevel(db)
        }
    }

    private func buildUI() {
        guard let contentView = window?.contentView else { return }
        contentView.translatesAutoresizingMaskIntoConstraints = false

        let root = NSStackView()
        root.orientation = .vertical
        root.alignment = .leading
        root.spacing = 12
        root.translatesAutoresizingMaskIntoConstraints = false

        statusLabel.font = .systemFont(ofSize: 20, weight: .semibold)
        connectionLabel.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        accessibilityLabel.font = .systemFont(ofSize: 12)
        doubaoInputLabel.font = .systemFont(ofSize: 12, weight: .medium)
        mappingLabel.font = .systemFont(ofSize: 13)

        root.addArrangedSubview(statusLabel)
        root.addArrangedSubview(connectionLabel)
        root.addArrangedSubview(accessibilityLabel)
        root.addArrangedSubview(doubaoInputLabel)
        root.addArrangedSubview(mappingLabel)

        let sourceTitle = NSTextField(labelWithString: "当前送入 vRemoteDr 2ch 的输入源")
        sourceTitle.font = .systemFont(ofSize: 14, weight: .semibold)
        root.addArrangedSubview(sourceTitle)

        macCheckbox.target = self
        macCheckbox.action = #selector(toggleMacInput)
        remoteCheckbox.target = self
        remoteCheckbox.action = #selector(toggleRemoteInput)
        root.addArrangedSubview(macCheckbox)
        root.addArrangedSubview(remoteCheckbox)

        let macMeter = makeMeterRow(title: "MacBook Air 麦克风电平", meter: macLevel)
        let remoteMeter = makeMeterRow(title: "X6 遥控器麦克风电平", meter: remoteLevel)
        root.addArrangedSubview(macMeter)
        root.addArrangedSubview(remoteMeter)

        let help = NSTextField(
            labelWithString: "两路始终同时采集并参与混音；电平不代表豆包内部状态。"
        )
        help.textColor = .secondaryLabelColor
        help.font = .systemFont(ofSize: 11)
        root.addArrangedSubview(help)

        let buttons = NSStackView()
        buttons.orientation = .horizontal
        buttons.spacing = 8
        let stop = NSButton(title: "关闭麦克风", target: self, action: #selector(stopMicrophone))
        let restart = NSButton(title: "重启 App", target: self, action: #selector(restartApp))
        let accessibility = NSButton(title: "打开辅助功能设置", target: self, action: #selector(openAccessibility))
        buttons.addArrangedSubview(stop)
        buttons.addArrangedSubview(restart)
        buttons.addArrangedSubview(accessibility)
        root.addArrangedSubview(buttons)

        contentView.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 24),
            root.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -24),
            root.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 24),
            root.bottomAnchor.constraint(lessThanOrEqualTo: contentView.bottomAnchor, constant: -24),
            macLevel.widthAnchor.constraint(equalToConstant: 430),
            remoteLevel.widthAnchor.constraint(equalToConstant: 430),
        ])
    }

    private func makeMeterRow(title: String, meter: NSLevelIndicator) -> NSStackView {
        meter.levelIndicatorStyle = .continuousCapacity
        meter.minValue = 0
        meter.maxValue = 1
        meter.warningValue = 0.65
        meter.criticalValue = 0.88
        meter.doubleValue = 0
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 12)
        let row = NSStackView(views: [label, meter])
        row.orientation = .horizontal
        row.spacing = 12
        return row
    }

    private static func normalizedLevel(_ db: Double) -> Double {
        max(0, min(1, (db + 60) / 60))
    }

    @objc private func toggleMacInput() {
        let enabled = macCheckbox.state == .on
        if !enabled {
            lastMacLevelDB = -120
            macLevel.doubleValue = 0
        }
        onMacInputEnabledChanged?(enabled)
    }

    @objc private func toggleRemoteInput() {
        let enabled = remoteCheckbox.state == .on
        if !enabled {
            lastRemoteLevelDB = -120
            remoteLevel.doubleValue = 0
        }
        onRemoteInputEnabledChanged?(enabled)
    }

    @objc private func stopMicrophone() {
        onStopMicrophone?()
    }

    @objc private func restartApp() {
        onRestartApp?()
    }

    @objc private func openAccessibility() {
        onOpenAccessibility?()
    }
}
