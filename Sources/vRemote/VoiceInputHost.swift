import Foundation

/// How the remote voice key drives the input method's recognition session.
///
/// Doubao Input Method exposes Option as a toggle, so one short tap opens and a
/// second tap closes. WeChat Input Method's default gesture is a held Fn, so the
/// trigger has to stay down while the user is talking.
enum VoiceTriggerStyle: String, CaseIterable, Identifiable {
    case tapToggle
    case pushToTalk

    var id: String { rawValue }

    var title: String {
        switch self {
        case .tapToggle: L10n.text("点按切换", "Tap to toggle")
        case .pushToTalk: L10n.text("长按说话", "Press and hold")
        }
    }

    var detail: String {
        switch self {
        case .tapToggle:
            L10n.text(
                "按一下开始，再按一下结束。",
                "Tap once to start, tap again to stop."
            )
        case .pushToTalk:
            L10n.text(
                "按住遥控器语音键说话，松开结束。",
                "Hold the remote voice key while talking."
            )
        }
    }
}

/// The input method that consumes the `vRemoteDr 2ch` capture stream.
///
/// vRemoter decides whether recognition is running by reading the input
/// method's own CoreAudio capture state, so the host has to be named here.
/// `automatic` watches every supported host at once and adopts whichever one is
/// actually recording, which keeps the app working when the user switches
/// input methods.
enum VoiceInputHost: String, CaseIterable, Identifiable {
    case automatic
    case doubao
    case weType

    var id: String { rawValue }

    var title: String {
        switch self {
        case .automatic: L10n.text("自动检测", "Automatic")
        case .doubao: L10n.text("豆包输入法", "Doubao Input Method")
        case .weType: L10n.text("微信输入法", "WeChat Input Method")
        }
    }

    /// Bundle IDs whose CoreAudio capture state should be observed.
    var bundleIDs: [String] {
        switch self {
        case .automatic: Self.doubao.bundleIDs + Self.weType.bundleIDs
        case .doubao: ["com.bytedance.inputmethod.doubaoime"]
        case .weType: ["com.tencent.inputmethod.wetype"]
        }
    }

    /// Human-readable name for a bundle ID reported by CoreAudio.
    static func title(forBundleID bundleID: String) -> String? {
        for host in [VoiceInputHost.doubao, .weType] where host.bundleIDs.contains(bundleID) {
            return host.title
        }
        return nil
    }
}

/// Trigger defaults that mirror each input method's own voice shortcut, so the
/// user does not have to configure the input method to match vRemoter.
enum VoiceInputDefaults {
    /// Doubao ships with Option; WeChat Input Method ships with Fn.
    static func triggerKey(for host: VoiceInputHost) -> InputTriggerKey? {
        switch host {
        case .automatic: nil
        case .doubao: .option
        case .weType: .function
        }
    }

    static func triggerStyle(for host: VoiceInputHost) -> VoiceTriggerStyle? {
        switch host {
        case .automatic: nil
        case .doubao: .tapToggle
        case .weType: .pushToTalk
        }
    }
}
