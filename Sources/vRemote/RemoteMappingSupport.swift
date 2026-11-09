import AppKit
import CoreGraphics
import Foundation

enum SupportedRemoteID: String, CaseIterable, Identifiable, Codable {
    case chromecast
    case x6

    var id: String { rawValue }

    var title: String {
        switch self {
        case .chromecast: "Chromecast Voice Remote"
        case .x6: "X6 Remote"
        }
    }

    var signature: String {
        switch self {
        case .chromecast: "18D1 · 9450"
        case .x6: "1D5A · C081"
        }
    }
}

struct RemoteButtonDefinition: Identifiable, Hashable {
    let id: String
    let title: String
    let symbol: String
    let defaultTarget: RemoteMappingTarget
    let voiceControlled: Bool
    let remappable: Bool

    init(
        id: String,
        title: String,
        symbol: String,
        defaultTarget: RemoteMappingTarget,
        voiceControlled: Bool = false,
        remappable: Bool = true
    ) {
        self.id = id
        self.title = title
        self.symbol = symbol
        self.defaultTarget = defaultTarget
        self.voiceControlled = voiceControlled
        self.remappable = remappable
    }
}

enum RemoteProfiles {
    static let chromecastButtons: [RemoteButtonDefinition] = [
        .init(id: "03", title: L10n.text("方向上", "Up"), symbol: "arrow.up", defaultTarget: .arrowUp),
        .init(id: "04", title: L10n.text("方向下", "Down"), symbol: "arrow.down", defaultTarget: .arrowDown),
        .init(id: "05", title: L10n.text("方向左", "Left"), symbol: "arrow.left", defaultTarget: .arrowLeft),
        .init(id: "06", title: L10n.text("方向右", "Right"), symbol: "arrow.right", defaultTarget: .arrowRight),
        .init(id: "07", title: L10n.text("确认", "Select"), symbol: "circle.inset.filled", defaultTarget: .returnKey),
        .init(id: "0B", title: L10n.text("返回", "Back"), symbol: "chevron.backward", defaultTarget: .escape),
        .init(id: "0A", title: "Home", symbol: "house", defaultTarget: .showDesktop),
        .init(id: "0E", title: "YouTube", symbol: "play.rectangle", defaultTarget: .disabled),
        .init(id: "voice", title: L10n.text("语音", "Voice"), symbol: "mic", defaultTarget: .doubaoVoice, voiceControlled: true),
        .init(id: "08", title: L10n.text("静音", "Mute"), symbol: "speaker.slash", defaultTarget: .mute),
        .init(id: "0F", title: "Netflix", symbol: "n.square", defaultTarget: .disabled),
        .init(id: "01", title: L10n.text("电源", "Power"), symbol: "power", defaultTarget: .disabled),
        .init(id: "11", title: L10n.text("信源", "Input"), symbol: "rectangle.on.rectangle", defaultTarget: .disabled),
        .init(id: "0C", title: L10n.text("音量＋", "Volume Up"), symbol: "speaker.plus", defaultTarget: .volumeUp),
        .init(id: "0D", title: L10n.text("音量－", "Volume Down"), symbol: "speaker.minus", defaultTarget: .volumeDown),
    ]

    static func buttons(for remote: SupportedRemoteID) -> [RemoteButtonDefinition] {
        switch remote {
        case .chromecast: chromecastButtons
        case .x6: x6Buttons
        }
    }

    static let x6Buttons: [RemoteButtonDefinition] = [
        .init(id: "mouseMode", title: L10n.text("鼠标模式", "Mouse Mode"), symbol: "cursorarrow.motionlines", defaultTarget: .disabled, remappable: false),
        .init(id: "k2A", title: "Delete", symbol: "delete.left", defaultTarget: .deleteBackward),
        .init(id: "cE2", title: L10n.text("静音", "Mute"), symbol: "speaker.slash", defaultTarget: .mute),
        .init(id: "c224", title: L10n.text("返回", "Back"), symbol: "chevron.backward", defaultTarget: .escape),
        .init(id: "k65", title: L10n.text("菜单", "Menu"), symbol: "line.3.horizontal", defaultTarget: .disabled),
        .init(id: "c196", title: L10n.text("浏览器/搜索", "Browser / Search"), symbol: "magnifyingglass", defaultTarget: .spotlight),
        .init(id: "k52", title: L10n.text("方向上", "Up"), symbol: "arrow.up", defaultTarget: .arrowUp),
        .init(id: "k51", title: L10n.text("方向下", "Down"), symbol: "arrow.down", defaultTarget: .arrowDown),
        .init(id: "k50", title: L10n.text("方向左", "Left"), symbol: "arrow.left", defaultTarget: .arrowLeft),
        .init(id: "k4F", title: L10n.text("方向右", "Right"), symbol: "arrow.right", defaultTarget: .arrowRight),
        .init(id: "k28", title: "OK", symbol: "circle.inset.filled", defaultTarget: .returnKey),
        .init(id: "k4B", title: "PG+", symbol: "arrow.up.to.line", defaultTarget: .pageUp),
        .init(id: "k4E", title: "PG−", symbol: "arrow.down.to.line", defaultTarget: .pageDown),
        .init(id: "voice", title: L10n.text("语音", "Voice"), symbol: "mic", defaultTarget: .doubaoVoice, voiceControlled: true),
        .init(id: "cE9", title: L10n.text("音量＋", "Volume Up"), symbol: "speaker.plus", defaultTarget: .volumeUp),
        .init(id: "cEA", title: L10n.text("音量－", "Volume Down"), symbol: "speaker.minus", defaultTarget: .volumeDown),
        .init(id: "s01", title: L10n.text("电源", "Power"), symbol: "power", defaultTarget: .disabled),
    ]
}

enum RemoteMappingTarget: String, CaseIterable, Identifiable, Codable, Hashable {
    case disabled
    case doubaoVoice
    case arrowUp
    case arrowDown
    case arrowLeft
    case arrowRight
    case returnKey
    case escape
    case deleteBackward
    case tab
    case space
    case home
    case end
    case pageUp
    case pageDown
    case volumeUp
    case volumeDown
    case mute
    case playPause
    case showDesktop
    case spotlight
    case commandC
    case commandV
    case commandZ
    case lockScreen
    case sleep
    case appSwitcher
    case mouseScroll
    case custom

    var id: String { rawValue }

    var title: String {
        switch self {
        case .disabled: L10n.text("禁用", "Disabled")
        case .doubaoVoice: L10n.text("豆包语音输入", "Doubao Voice Input")
        case .arrowUp: L10n.text("方向上", "Up Arrow")
        case .arrowDown: L10n.text("方向下", "Down Arrow")
        case .arrowLeft: L10n.text("方向左", "Left Arrow")
        case .arrowRight: L10n.text("方向右", "Right Arrow")
        case .returnKey: "Return"
        case .escape: "Escape"
        case .deleteBackward: "Delete"
        case .tab: "Tab"
        case .space: L10n.text("空格", "Space")
        case .home: "Home"
        case .end: "End"
        case .pageUp: "Page Up"
        case .pageDown: "Page Down"
        case .volumeUp: L10n.text("系统音量＋", "System Volume Up")
        case .volumeDown: L10n.text("系统音量－", "System Volume Down")
        case .mute: L10n.text("系统静音", "System Mute")
        case .playPause: L10n.text("播放/暂停", "Play / Pause")
        case .showDesktop: L10n.text("显示桌面", "Show Desktop")
        case .spotlight: "Spotlight (⌘Space)"
        case .commandC: L10n.text("复制 (⌘C)", "Copy (⌘C)")
        case .commandV: L10n.text("粘贴 (⌘V)", "Paste (⌘V)")
        case .commandZ: L10n.text("撤销 (⌘Z)", "Undo (⌘Z)")
        case .lockScreen: L10n.text("锁屏", "Lock Screen")
        case .sleep: L10n.text("睡眠", "Sleep")
        case .appSwitcher: L10n.text("切换应用", "App Switcher")
        case .mouseScroll: L10n.text("鼠标滚动…", "Mouse Scroll…")
        case .custom: L10n.text("录制任意按键…", "Record a key…")
        }
    }

    var keyboard: (keyCode: CGKeyCode, flags: CGEventFlags)? {
        switch self {
        case .arrowUp: (0x7E, [])
        case .arrowDown: (0x7D, [])
        case .arrowLeft: (0x7B, [])
        case .arrowRight: (0x7C, [])
        case .returnKey: (0x24, [])
        case .escape: (0x35, [])
        case .deleteBackward: (0x33, [])
        case .tab: (0x30, [])
        case .space: (0x31, [])
        case .home: (0x73, [])
        case .end: (0x77, [])
        case .pageUp: (0x74, [])
        case .pageDown: (0x79, [])
        case .showDesktop: (0x67, [.maskSecondaryFn])
        case .spotlight: (0x31, [.maskCommand])
        case .commandC: (0x08, [.maskCommand])
        case .commandV: (0x09, [.maskCommand])
        case .commandZ: (0x06, [.maskCommand])
        case .lockScreen: (0x0C, CGEventFlags(rawValue: CGEventFlags.maskControl.rawValue | CGEventFlags.maskCommand.rawValue | 0x12))
        // 0x0C = Q 键（⌃⌘Q = 系统锁屏热键）。锁屏热键由 loginwindow 在 IOKit 设备层匹配，
        // 合成事件需附设备相关修饰位：0x2 = Left-Control，0x10 = Left-Command。
        default: nil
        }
    }

    var mediaKey: Int32? {
        switch self {
        case .volumeUp: 0
        case .volumeDown: 1
        case .mute: 7
        case .playPause: 16
        default: nil
        }
    }

    func post(isDown: Bool) {
        guard self != .disabled, self != .doubaoVoice else { return }
        switch self {
        case .sleep:
            // 睡眠：无可靠组合键，走 System Events（首次触发 macOS TCC 授权）。
            // 仅 keyDown 触发一次，keyUp 忽略。
            if isDown { AppSwitcherSupport.requestSystemSleep() }
        case .appSwitcher:
            // 切换应用：按下=开启/延续会话（⌘ 虚拟按住），松手无动作，由 1s 倒计时收尾。
            if isDown { AppSwitcherSession.shared.tapSwitcher() }
        default:
            if let keyboard {
                let source = CGEventSource(stateID: .hidSystemState)
                guard let event = CGEvent(
                    keyboardEventSource: source,
                    virtualKey: keyboard.keyCode,
                    keyDown: isDown
                ) else { return }
                event.flags = keyboard.flags
                event.setIntegerValueField(.eventSourceUserData, value: Key.syntheticMarker)
                event.post(tap: .cghidEventTap)
            } else if let mediaKey, isDown {
                postMediaKey(mediaKey)
            }
        }
    }

    private func postMediaKey(_ key: Int32) {
        func post(state: Int32) {
            let data1 = Int((key << 16) | (state << 8))
            guard let event = NSEvent.otherEvent(
                with: .systemDefined,
                location: .zero,
                modifierFlags: [],
                timestamp: 0,
                windowNumber: 0,
                context: nil,
                subtype: 8,
                data1: data1,
                data2: -1
            )?.cgEvent else { return }
            event.post(tap: .cghidEventTap)
        }
        post(state: 0xA)
        post(state: 0xB)
    }
}

struct RemoteCustomShortcut: Codable, Hashable {
    let keyCode: UInt16
    let flags: UInt64
    let label: String

    func post(isDown: Bool) {
        let source = CGEventSource(stateID: .hidSystemState)
        guard let event = CGEvent(
            keyboardEventSource: source,
            virtualKey: CGKeyCode(keyCode),
            keyDown: isDown
        ) else { return }
        event.flags = CGEventFlags(rawValue: flags)
        event.setIntegerValueField(.eventSourceUserData, value: Key.syntheticMarker)
        event.post(tap: .cghidEventTap)
    }
}

/// 鼠标滚动映射配置：方向（正=向上 / 负=向下）与单次滚动量（行）。
struct RemoteScrollConfig: Codable, Hashable {
    let up: Bool
    let amount: Int32

    var label: String {
        let arrow = up ? "↑" : "↓"
        return L10n.text(
            "滚动\(arrow)\(amount) 行",
            "Scroll \(arrow)\(amount) line(s)"
        )
    }

    /// 连发 tick 与按下各发一次滚轮事件；松手无动作。
    func post(isDown: Bool) {
        guard isDown, amount != 0 else { return }
        guard let event = CGEvent(
            scrollWheelEvent2Source: CGEventSource(stateID: .hidSystemState),
            units: .line,
            wheelCount: 1,
            wheel1: up ? amount : -amount,
            wheel2: 0,
            wheel3: 0
        ) else { return }
        event.setIntegerValueField(.eventSourceUserData, value: Key.syntheticMarker)
        event.post(tap: .cghidEventTap)
    }
}

/// 切换应用会话：⌘ 虚拟按住 + Tab 发射 + 1s 倒计时自动收尾。
/// 不依赖长按松手边沿，X6 / Chromecast 共用同一交互。
///
/// ⚠️ 收尾定时用 GCD 主队列（DispatchWorkItem），不用 Timer.scheduledTimer——
/// HID 回调在后台线程，后台 RunLoop 不跑 timer mode，定时器会永远不触发。
final class AppSwitcherSession {
    static let shared = AppSwitcherSession()

    /// 倒计时时长：会话内任何一次会话键按下都会重置。
    static let idleInterval: TimeInterval = 1.0

    private(set) var isActive = false
    private var pending: DispatchWorkItem?

    private var source: CGEventSource? { CGEventSource(stateID: .hidSystemState) }

    /// 切换应用键按下：首次=开启会话（⌘↓ + Tab），会话中=再发一次 Tab（等同连按 Tab）。
    func tapSwitcher() {
        if isActive {
            tapTab(shift: false)
        } else {
            isActive = true
            postKey(55, flags: [.maskCommand], down: true)
            tapTab(shift: false)
        }
        schedule()
    }

    /// 方向键重定向入口。返回 false 表示会话未激活，调用方按原逻辑处理。
    func redirectArrow(isRight: Bool) {
        guard isActive else { return }
        tapTab(shift: !isRight)
        schedule()
    }

    /// 会话收尾（⌘↑）或外部取消。幂等。
    func cancel() {
        pending?.cancel()
        pending = nil
        guard isActive else { return }
        isActive = false
        // ⌘↑ 事件的 flags 必须为空（表示释放后无任何修饰键按下）；
        // 若仍带 .maskCommand，系统会认为 ⌘ 还按着，切换器永远不会关闭。
        postKey(55, flags: [], down: false)
    }

    private func tapTab(shift: Bool) {
        var flags: CGEventFlags = [.maskCommand]
        if shift { flags.insert(.maskShift) }
        postKey(48, flags: flags, down: true)
        postKey(48, flags: flags, down: false)
    }

    private func schedule() {
        pending?.cancel()
        let item = DispatchWorkItem { [weak self] in
            self?.cancel()
        }
        pending = item
        DispatchQueue.main.asyncAfter(
            deadline: .now() + Self.idleInterval,
            execute: item
        )
    }

    private func postKey(_ keyCode: CGKeyCode, flags: CGEventFlags, down: Bool) {
        guard let event = CGEvent(
            keyboardEventSource: source,
            virtualKey: keyCode,
            keyDown: down
        ) else { return }
        event.flags = flags
        event.setIntegerValueField(.eventSourceUserData, value: Key.syntheticMarker)
        event.post(tap: .cghidEventTap)
    }
}

enum AppSwitcherSupport {
    /// 睡眠：无可靠系统组合键（pmset/IOKit 均需 root），走 System Events。
    /// 首次触发时 macOS 会弹一次 TCC 授权（vRemote → System Events）。
    static func requestSystemSleep() {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = ["-e", "tell application \"System Events\" to sleep"]
        try? task.run()
    }
}

final class RemoteMappingStore: ObservableObject {
    static let shared = RemoteMappingStore()

    @Published private(set) var revision = 0
    private let defaults = UserDefaults.standard
    private let prefix = "remoteMapping."
    private let enabledPrefix = "remoteMappingEnabled."
    private let customPrefix = "remoteCustomMapping."
    private let scrollPrefix = "remoteScrollMapping."

    private init() {}

    func isEnabled(_ remote: SupportedRemoteID) -> Bool {
        defaults.bool(forKey: enabledPrefix + remote.rawValue)
    }

    func setEnabled(_ enabled: Bool, for remote: SupportedRemoteID) {
        defaults.set(enabled, forKey: enabledPrefix + remote.rawValue)
        revision += 1
    }

    func target(
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) -> RemoteMappingTarget {
        guard !button.voiceControlled else { return .doubaoVoice }
        guard button.remappable else { return .disabled }
        let key = prefix + remote.rawValue + "." + button.id
        guard let raw = defaults.string(forKey: key),
              let target = RemoteMappingTarget(rawValue: raw)
        else { return button.defaultTarget }
        return target
    }

    func setTarget(
        _ target: RemoteMappingTarget,
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) {
        guard !button.voiceControlled, button.remappable else { return }
        defaults.set(
            target.rawValue,
            forKey: prefix + remote.rawValue + "." + button.id
        )
        revision += 1
    }

    func customShortcut(
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) -> RemoteCustomShortcut? {
        let key = customPrefix + remote.rawValue + "." + button.id
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(RemoteCustomShortcut.self, from: data)
    }

    func setCustomShortcut(
        _ shortcut: RemoteCustomShortcut,
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) {
        let key = customPrefix + remote.rawValue + "." + button.id
        if let data = try? JSONEncoder().encode(shortcut) {
            defaults.set(data, forKey: key)
            setTarget(.custom, for: button, remote: remote)
        }
    }

    func scrollConfig(
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) -> RemoteScrollConfig {
        let key = scrollPrefix + remote.rawValue + "." + button.id
        guard let data = defaults.data(forKey: key),
              let config = try? JSONDecoder().decode(
                RemoteScrollConfig.self, from: data
              )
        else { return RemoteScrollConfig(up: false, amount: 3) }
        return config
    }

    func setScrollConfig(
        _ config: RemoteScrollConfig,
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) {
        guard !button.voiceControlled, button.remappable else { return }
        if let data = try? JSONEncoder().encode(config) {
            defaults.set(data, forKey: scrollPrefix + remote.rawValue + "." + button.id)
        }
        revision += 1
    }

    func targetTitle(
        for button: RemoteButtonDefinition,
        remote: SupportedRemoteID
    ) -> String {
        let value = target(for: button, remote: remote)
        if value == .custom,
           let shortcut = customShortcut(for: button, remote: remote) {
            return shortcut.label
        }
        if value == .mouseScroll {
            return scrollConfig(for: button, remote: remote).label
        }
        return value.title
    }

    /// 长按自动连发：合成 CGEvent 不会像物理键盘那样被 macOS 自动重复，
    /// 遥控器也不发 HID repeat 报告，因此按住时由 app 层重发 keyDown。
    /// 用 GCD 主队列（同 AppSwitcherSession 的原因：HID 回调在后台线程，
    /// Timer 在后台 RunLoop 不会触发）。
    private struct RepeatKey: Hashable {
        let remote: SupportedRemoteID
        let buttonID: String
    }
    private static let repeatInitialDelay: TimeInterval = 0.5
    private static let repeatInterval: TimeInterval = 0.06
    private var repeatTimers: [RepeatKey: DispatchWorkItem] = [:]

    private func cancelRepeat(for key: RepeatKey) {
        repeatTimers.removeValue(forKey: key)?.cancel()
    }

    /// 键盘类目标（方向键 / Return / 自定义快捷键 / 鼠标滚动）支持长按连发。
    private func supportsRepeat(_ target: RemoteMappingTarget) -> Bool {
        target.keyboard != nil || target == .custom || target == .mouseScroll
    }

    func post(
        button: RemoteButtonDefinition,
        remote: SupportedRemoteID,
        isDown: Bool
    ) {
        let key = RepeatKey(remote: remote, buttonID: button.id)
        cancelRepeat(for: key)

        /// 触发一次按下动作。松手边沿传 isDown=false（连发只重发 keyDown）。
        func pressOnce(isDown: Bool) {
            let value = target(for: button, remote: remote)
            // 切换器会话期间：方向键左右重定向为 Tab / Shift+Tab（仅 keyDown 生效）。
            // 连发定时器撞上会话时直接跳过，避免长按方向键在切换器里狂发 Tab。
            if AppSwitcherSession.shared.isActive,
               value == .arrowLeft || value == .arrowRight {
                if isDown {
                    AppSwitcherSession.shared.redirectArrow(isRight: value == .arrowRight)
                }
                return
            }
            if value == .custom {
                customShortcut(for: button, remote: remote)?.post(isDown: isDown)
            } else if value == .mouseScroll {
                // 滚动只在按下/连发 tick 产生事件，松手无动作。
                if isDown {
                    scrollConfig(for: button, remote: remote)?.post(isDown: true)
                }
            } else {
                value.post(isDown: isDown)
            }
        }

        pressOnce(isDown: isDown)
        guard isDown,
              supportsRepeat(target(for: button, remote: remote))
        else { return }

        let tick: (Bool) -> Void = { [weak self] isInitial in
            guard let self, self.repeatTimers[key]?.isCancelled != true else { return }
            guard AppSwitcherSession.shared.isActive == false else {
                self.cancelRepeat(for: key)
                return
            }
            if !isInitial { pressOnce(isDown: true) }
            DispatchQueue.main.asyncAfter(
                deadline: .now() + (isInitial
                    ? Self.repeatInitialDelay
                    : Self.repeatInterval),
                execute: DispatchWorkItem { tick(false) }
            )
        }
        repeatTimers[key] = DispatchWorkItem {}
        tick(true)
    }

    func reset(_ remote: SupportedRemoteID) {
        for button in RemoteProfiles.buttons(for: remote) {
            defaults.removeObject(
                forKey: prefix + remote.rawValue + "." + button.id
            )
            defaults.removeObject(
                forKey: customPrefix + remote.rawValue + "." + button.id
            )
            defaults.removeObject(
                forKey: scrollPrefix + remote.rawValue + "." + button.id
            )
        }
        revision += 1
    }
}
