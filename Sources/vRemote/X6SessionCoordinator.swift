import Foundation

/// Coordinates three independent signals without feeding one back into
/// another:
///
/// 1. A physical keyboard Option is delivered to Doubao by macOS. We only
///    follow it by opening/closing the X6 microphone; we never synthesize a
///    second Option for it.
/// 2. X6 has no dependable HID edge on its first tap, but it does start an
///    ATVV stream. An unsolicited AUDIO_START therefore creates exactly one
///    synthetic Option click.
/// 3. AUDIO_START/AUDIO_STOP after a requested microphone transition are
///    transport confirmations only. They never create another key event.
final class X6SessionCoordinator {
    private enum Owner: String {
        case none
        case x6
        case keyboard
    }

    private let doubaoState: DoubaoAudioStateMonitor

    private var owner: Owner = .none
    private var routeActive = false
    private var transportStreaming = false
    private var transportOpenRequested = false
    private var optionRequestedOpen = false
    private var recognitionExpectedOpen = false
    private var closeOptionSent = false
    private var closeWorkItem: DispatchWorkItem?
    private var startVerificationWorkItem: DispatchWorkItem?

    var onMicrophoneOpenRequested: (() -> Void)?
    var onMicrophoneCloseRequested: (() -> Void)?
    var onStateChanged: ((String) -> Void)?

    init(doubaoState: DoubaoAudioStateMonitor) {
        self.doubaoState = doubaoState
    }

    func start() {
        doubaoState.onSnapshotChanged = { [weak self] snapshot in
            self?.handleDoubaoSnapshot(snapshot)
        }
        doubaoState.start()
    }

    // MARK: - ATVV transport

    func remoteAudioStarted(
        reason: UInt8,
        toggleOnRepeatedPhysicalStart: Bool = false
    ) {
        let snapshot = doubaoState.snapshotNow()

        // A host-requested persistent stream can already be active when the
        // user presses Chromecast Remote's voice key a second time. Handle
        // the physical 0x03 edge before duplicate-stream filtering, otherwise
        // that reliable toggle-off gesture is discarded as another START.
        if toggleOnRepeatedPhysicalStart,
           reason == 0x03,
           (recognitionExpectedOpen || snapshot.isRecording)
        {
            closeRecognitionFromRemote(reason: "ATVV TOGGLE")
            return
        }

        guard !transportStreaming else {
            print(
                "[X6-SESSION] duplicate AUDIO_START ignored reason=" +
                String(format: "0x%02x", reason)
            )
            return
        }
        transportStreaming = true
        transportOpenRequested = false
        activateRemoteRoute(requestTransportOpen: false)

        print(
            "[X6-SESSION] AUDIO_START reason=" +
            String(format: "0x%02x", reason) +
            " owner=\(owner.rawValue) " +
            "doubaoBefore=\(snapshot.state.rawValue) " +
            "device=\(snapshot.deviceSummary)"
        )

        // A keyboard Option requested this stream. The physical Option has
        // already reached Doubao, so AUDIO_START is confirmation only.
        if owner == .keyboard {
            publish("豆包录音中 · 遥控器已接入")
            return
        }

        // An already-open X6 session must not be toggled by a duplicate or
        // late transport notification.
        guard !recognitionExpectedOpen, !optionRequestedOpen else {
            print("[X6-SESSION] AUDIO_START confirmation; no Option generated")
            return
        }

        owner = .x6
        recognitionExpectedOpen = true
        optionRequestedOpen = true
        closeOptionSent = false
        Key.optionTap()
        publish("遥控器已启动 · 正在打开豆包")
        scheduleStartVerification()
        reconcileSoon(after: 0.03)
        reconcileSoon(after: 0.15)
    }

    func remoteAudioStopped(reason: UInt8) {
        guard transportStreaming else {
            print(
                "[X6-SESSION] duplicate AUDIO_STOP ignored reason=" +
                String(format: "0x%02x", reason)
            )
            return
        }
        transportStreaming = false
        transportOpenRequested = false
        print(
            "[X6-SESSION] AUDIO_STOP reason=" +
            String(format: "0x%02x", reason) +
            " owner=\(owner.rawValue) expectedOpen=\(recognitionExpectedOpen)"
        )

        // A transport stop is never a keyboard event. Closing Doubao here
        // caused the previous close/open feedback loop.
        if recognitionExpectedOpen {
            publish("豆包仍开启 · 遥控器音频已停止")
        } else {
            scheduleRouteClose()
        }
    }

    // MARK: - X6 HID completion

    /// The first X6 tap is represented by AUDIO_START. The next HID gesture
    /// is the explicit toggle-off action.
    func remoteHIDShortPress() {
        closeRecognitionFromRemote(reason: "HID SHORT")
    }

    func remoteHIDLongPressEnded() {
        closeRecognitionFromRemote(reason: "HID LONG release")
    }

    // MARK: - Physical keyboard Option

    /// Called before a real keyboard Option DOWN reaches Doubao. This method
    /// follows the physical key by changing microphone transport only.
    func optionDownObserved(isSynthetic: Bool) {
        guard !isSynthetic else { return }
        let snapshot = doubaoState.snapshotNow()
        let wasOpen = recognitionExpectedOpen || snapshot.isRecording
        print(
            "[OPTION] DOWN source=keyboard action=" +
            (wasOpen ? "close" : "open") +
            " doubaoBefore=\(snapshot.state.rawValue) " +
            "device=\(snapshot.deviceSummary)"
        )

        startVerificationWorkItem?.cancel()
        startVerificationWorkItem = nil

        if wasOpen {
            owner = .none
            recognitionExpectedOpen = false
            optionRequestedOpen = false
            closeOptionSent = false
            scheduleRouteClose(after: 0.08)
            publish("豆包正在结束")
        } else {
            owner = .keyboard
            recognitionExpectedOpen = true
            optionRequestedOpen = true
            closeOptionSent = false
            activateRemoteRoute(requestTransportOpen: true)
            scheduleStartVerification()
            publish("豆包正在启动 · 遥控器已预热")
        }
    }

    func optionUpObserved(isSynthetic: Bool) {
        guard !isSynthetic else { return }
        print("[OPTION] UP source=keyboard owner=\(owner.rawValue)")
        reconcileSoon(after: 0.03)
        reconcileSoon(after: 0.15)
    }

    // MARK: - Lifecycle / manual control

    func forceClose() {
        startVerificationWorkItem?.cancel()
        startVerificationWorkItem = nil
        closeWorkItem?.cancel()
        closeWorkItem = nil
        owner = .none
        optionRequestedOpen = false
        recognitionExpectedOpen = false
        closeOptionSent = false
        closeRouteAndTransport()
        publish("已手动关闭")
    }

    func stop() {
        forceClose()
        doubaoState.stop()
    }

    // MARK: - Doubao observation

    private func handleDoubaoSnapshot(
        _ snapshot: DoubaoAudioStateMonitor.Snapshot
    ) {
        switch snapshot.state {
        case .active:
            startVerificationWorkItem?.cancel()
            startVerificationWorkItem = nil
            optionRequestedOpen = false
            // Some macOS keyboard paths deliver only the physical Option UP
            // edge to our event tap. Doubao's real CoreAudio transition is a
            // second, independent source of truth: if it starts recording
            // while no vRemote session is expected, treat that as an external
            // (keyboard/IME) open and follow it with the audio route.
            if !recognitionExpectedOpen {
                owner = .keyboard
                recognitionExpectedOpen = true
                closeOptionSent = false
                print(
                    "[X6-SESSION] Doubao external activation → " +
                    "open vRemote route and X6 microphone"
                )
            }
            activateRemoteRoute(requestTransportOpen: !transportStreaming)
            publish("豆包录音中 · \(snapshot.deviceSummary)")

        case .inactive:
            // During an opening transition CoreAudio can briefly remain idle.
            // The verification timer owns that timeout.
            if optionRequestedOpen { return }

            if recognitionExpectedOpen {
                print(
                    "[X6-SESSION] Doubao became inactive; " +
                    "owner=\(owner.rawValue)"
                )
                owner = .none
                recognitionExpectedOpen = false
            }
            scheduleRouteClose()
            publish("豆包已就绪")

        case .unavailable:
            if !optionRequestedOpen {
                scheduleRouteClose()
            }
            publish("等待豆包输入法")
        }
    }

    private func closeRecognitionFromRemote(reason: String) {
        guard recognitionExpectedOpen, !closeOptionSent else {
            print(
                "[X6-SESSION] \(reason) ignored; " +
                "owner=\(owner.rawValue) " +
                "expectedOpen=\(recognitionExpectedOpen) " +
                "closeSent=\(closeOptionSent)"
            )
            return
        }
        startVerificationWorkItem?.cancel()
        startVerificationWorkItem = nil
        closeOptionSent = true
        recognitionExpectedOpen = false
        optionRequestedOpen = false
        owner = .none
        Key.optionTap()
        scheduleRouteClose(after: 0.10)
        publish("遥控器已结束 · 正在关闭豆包")
        print("[X6-SESSION] \(reason) → one Option TAP OFF")
    }

    private func scheduleStartVerification() {
        startVerificationWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.startVerificationWorkItem = nil
            let snapshot = self.doubaoState.snapshotNow()
            if snapshot.isRecording {
                self.handleDoubaoSnapshot(snapshot)
                return
            }
            self.owner = .none
            self.optionRequestedOpen = false
            self.recognitionExpectedOpen = false
            self.scheduleRouteClose()
            self.publish("豆包未启动 · 遥控器自动关闭")
            print(
                "[X6-SESSION] Option 后豆包未进入录音状态; " +
                "state=\(snapshot.state.rawValue)"
            )
        }
        startVerificationWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: work)
    }

    private func activateRemoteRoute(requestTransportOpen: Bool) {
        closeWorkItem?.cancel()
        closeWorkItem = nil
        if !routeActive {
            routeActive = true
            AudioPipe.shared.setRemoteActive(true)
            print("[X6-SESSION] X6 audio route ON owner=\(owner.rawValue)")
        }

        guard requestTransportOpen,
              !transportStreaming,
              !transportOpenRequested
        else { return }
        transportOpenRequested = true
        onMicrophoneOpenRequested?()
        print("[X6-SESSION] MIC_OPEN requested owner=\(owner.rawValue)")
    }

    private func reconcileSoon(after delay: TimeInterval) {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            self.handleDoubaoSnapshot(self.doubaoState.snapshotNow())
        }
    }

    private func scheduleRouteClose(after delay: TimeInterval = 0.16) {
        closeWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.closeWorkItem = nil
            self.closeRouteAndTransport()
            self.publish("豆包已就绪")
        }
        closeWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func closeRouteAndTransport() {
        let shouldCloseTransport = transportStreaming || transportOpenRequested
        routeActive = false
        transportOpenRequested = false
        AudioPipe.shared.setRemoteActive(false)
        if shouldCloseTransport {
            onMicrophoneCloseRequested?()
            print("[X6-SESSION] MIC_CLOSE requested")
        }
        print("[X6-SESSION] X6 audio route OFF")
    }

    private func publish(_ status: String) {
        onStateChanged?(status)
    }
}
