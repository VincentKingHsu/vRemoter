import Carbon
import Foundation

/// The Mac voice-typing tool that the remote voice key drives.
///
/// This table is the single source of truth for per-tool behavior. UI copy,
/// default trigger keys, input-source switching and session verification all
/// derive from it; do not special-case a tool anywhere else.
enum VoiceInputTool: String, CaseIterable, Identifiable {
    case doubao
    case wetype
    case custom

    var id: String { rawValue }

    var title: String {
        switch self {
        case .doubao: L10n.text("豆包输入法", "Doubao Input Method")
        case .wetype: L10n.text("微信输入法", "WeType")
        case .custom: L10n.text("其他语音工具", "Other voice tool")
        }
    }

    /// Short name used inside status sentences ("豆包录音中").
    var shortName: String {
        switch self {
        case .doubao: L10n.text("豆包", "Doubao")
        case .wetype: L10n.text("微信输入法", "WeType")
        case .custom: L10n.text("语音工具", "Voice tool")
        }
    }

    /// The trigger applied when the user switches to this tool. Users can
    /// still pick another key; it must match the tool's own voice shortcut.
    /// WeType: an Fn tap toggles voice input (verified with a remote on
    /// 2026-11-05).
    var defaultTrigger: InputTriggerKey {
        switch self {
        case .doubao: .option
        case .wetype: .function
        case .custom: .option
        }
    }

    /// The TIS input source that owns the voice shortcut, when the tool is an
    /// input method.
    var inputSourceID: String? {
        switch self {
        case .doubao: "com.bytedance.inputmethod.doubaoime.pinyin"
        case .wetype: "com.tencent.inputmethod.wetype.pinyin"
        case .custom: nil
        }
    }

    /// Whether a remote-started session first selects `inputSourceID`.
    /// An input method only sees its shortcut while it is the active input
    /// source. Doubao keeps its verified global-activation behavior.
    var switchesInputSourceForVoice: Bool {
        switch self {
        case .doubao: false
        case .wetype: true
        case .custom: false
        }
    }

    /// Whether vRemoter can read the tool's real CoreAudio recording state.
    /// When false, the session follows the voice gestures without
    /// verification (open on the opening gesture, closed on the closing one).
    var observesRecordingState: Bool {
        self == .doubao
    }

    /// Verified tools have passed an end-to-end remote test on macOS.
    /// Unverified tools are shown with an explicit "unverified" label.
    var isVerified: Bool {
        self != .custom
    }

    /// Label for the remote voice key in the mapping list.
    var voiceActionTitle: String {
        switch self {
        case .doubao: L10n.text("豆包语音输入", "Doubao Voice Input")
        case .wetype: L10n.text("微信输入法语音输入", "WeType Voice Input")
        case .custom: L10n.text("语音工具快捷键", "Voice Tool Shortcut")
        }
    }

    static var selected: VoiceInputTool {
        get { AppStorage.voiceInputTool }
        set { AppStorage.voiceInputTool = newValue }
    }
}

enum VoiceTriggerIntent {
    case open
    case close
}

/// Selects a voice tool's input source for the duration of a remote-started
/// voice session and restores the user's previous input source afterwards.
final class VoiceInputSourceSession {
    private static let activationTimeout: TimeInterval = 0.5
    private static let activationPollInterval: TimeInterval = 0.02
    private static let restoreDelay: TimeInterval = 0.3

    private var previousInputSourceID: String?
    private var activeTargetID: String?

    /// Selects the tool's input source if needed, then runs `then` once it
    /// is active (or after a bounded wait if macOS has not switched yet).
    func prepare(for tool: VoiceInputTool, then: @escaping () -> Void) {
        guard tool.switchesInputSourceForVoice,
              let targetID = tool.inputSourceID
        else {
            then()
            return
        }
        let current = Self.currentInputSourceID()
        if current == targetID {
            then()
            return
        }
        guard let source = Self.inputSource(withID: targetID) else {
            print("[INPUT-SOURCE] \(targetID) is not enabled; trigger sent as-is")
            then()
            return
        }
        guard TISSelectInputSource(source) == noErr else {
            print("[INPUT-SOURCE] failed to select \(targetID)")
            then()
            return
        }
        if activeTargetID == nil {
            previousInputSourceID = current
        }
        activeTargetID = targetID
        print(
            "[INPUT-SOURCE] selected \(targetID) previous=\(current ?? "-")"
        )
        waitUntilActive(
            targetID,
            deadline: Date().addingTimeInterval(Self.activationTimeout),
            then: then
        )
    }

    /// Restores the input source that was active before `prepare`, unless
    /// the user has switched to another input source in the meantime.
    func restore() {
        guard let targetID = activeTargetID else { return }
        let previousID = previousInputSourceID
        activeTargetID = nil
        previousInputSourceID = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.restoreDelay) {
            guard let previousID,
                  previousID != targetID,
                  Self.currentInputSourceID() == targetID,
                  let source = Self.inputSource(withID: previousID)
            else { return }
            let status = TISSelectInputSource(source)
            print(
                "[INPUT-SOURCE] restored \(previousID) " +
                "status=\(status == noErr ? "OK" : String(status))"
            )
        }
    }

    /// Whether the tool's input source is installed and enabled.
    static func isAvailable(_ tool: VoiceInputTool) -> Bool? {
        guard let targetID = tool.inputSourceID else { return nil }
        return inputSource(withID: targetID) != nil
    }

    static func currentInputSourceID() -> String? {
        let current = TISCopyCurrentKeyboardInputSource().takeRetainedValue()
        return stringProperty(kTISPropertyInputSourceID, from: current)
    }

    private func waitUntilActive(
        _ targetID: String,
        deadline: Date,
        then: @escaping () -> Void
    ) {
        if Self.currentInputSourceID() == targetID || Date() >= deadline {
            then()
            return
        }
        DispatchQueue.main.asyncAfter(
            deadline: .now() + Self.activationPollInterval
        ) { [weak self] in
            guard let self else {
                then()
                return
            }
            self.waitUntilActive(targetID, deadline: deadline, then: then)
        }
    }

    private static func inputSource(withID targetID: String) -> TISInputSource? {
        let sources = TISCreateInputSourceList(nil, false)
            .takeRetainedValue() as NSArray
        for case let source as TISInputSource in sources
        where stringProperty(kTISPropertyInputSourceID, from: source) == targetID {
            return source
        }
        return nil
    }

    private static func stringProperty(
        _ key: CFString,
        from source: TISInputSource
    ) -> String? {
        guard let pointer = TISGetInputSourceProperty(source, key) else {
            return nil
        }
        return Unmanaged<CFTypeRef>
            .fromOpaque(pointer)
            .takeUnretainedValue() as? String
    }
}
