#if DEBUG
import CoreAudio
import Foundation

enum VoiceSessionSelfTest {
    private final class FakeDoubaoState: DoubaoAudioStateProviding {
        var onSnapshotChanged: ((DoubaoAudioStateMonitor.Snapshot) -> Void)?
        private(set) var snapshot: DoubaoAudioStateMonitor.Snapshot

        init(state: DoubaoAudioStateMonitor.State = .inactive) {
            snapshot = Self.makeSnapshot(state)
        }

        func start() {}
        func stop() {}

        func snapshotNow() -> DoubaoAudioStateMonitor.Snapshot {
            snapshot
        }

        func emit(_ state: DoubaoAudioStateMonitor.State) {
            snapshot = Self.makeSnapshot(state)
            onSnapshotChanged?(snapshot)
        }

        private static func makeSnapshot(
            _ state: DoubaoAudioStateMonitor.State
        ) -> DoubaoAudioStateMonitor.Snapshot {
            DoubaoAudioStateMonitor.Snapshot(
                state: state,
                pid: 123,
                processObjectID: 456,
                inputDeviceIDs: state == .active ? [789] : [],
                inputDeviceNames: state == .active ? ["vRemoteDr 2ch"] : []
            )
        }
    }

    private final class Harness {
        let doubao: FakeDoubaoState
        let coordinator: X6SessionCoordinator
        var clock = Date(timeIntervalSince1970: 1_000)
        var triggerTapCount = 0
        var triggerIntents = [VoiceTriggerIntent]()
        var sessionFinishedCount = 0
        var routeChanges = [Bool]()
        var openRequests = [(VoiceRemoteID, Bool)]()
        var closeRequestCount = 0
        var openResults = [RemoteMicrophoneOpenResult]()
        var preferredRemote: VoiceRemoteID? = .chromecast

        init(
            initialState: DoubaoAudioStateMonitor.State = .inactive,
            observesToolState: Bool = true
        ) {
            doubao = FakeDoubaoState(state: initialState)
            var routeSink: ((Bool) -> Void)?
            var triggerSink: ((VoiceTriggerIntent) -> Void)?
            var nowSink: (() -> Date)?
            coordinator = X6SessionCoordinator(
                doubaoState: doubao,
                setRemoteRouteActive: { routeSink?($0) },
                triggerTap: { triggerSink?($0) },
                observesToolState: { observesToolState },
                toolName: { "TestTool" },
                now: { nowSink?() ?? Date(timeIntervalSince1970: 0) }
            )
            routeSink = { [weak self] active in
                self?.routeChanges.append(active)
            }
            triggerSink = { [weak self] intent in
                self?.triggerTapCount += 1
                self?.triggerIntents.append(intent)
            }
            nowSink = { [weak self] in
                self?.clock ?? Date(timeIntervalSince1970: 0)
            }
            coordinator.preferredRemoteProvider = { [weak self] in
                self?.preferredRemote
            }
            coordinator.onMicrophoneOpenRequested = {
                [weak self] remote, bypass in
                guard let self else { return .unavailable }
                self.openRequests.append((remote, bypass))
                return self.openResults.isEmpty
                    ? .sent
                    : self.openResults.removeFirst()
            }
            coordinator.onMicrophoneCloseRequested = { [weak self] in
                self?.closeRequestCount += 1
            }
            coordinator.onSessionFinished = { [weak self] in
                self?.sessionFinishedCount += 1
            }
            coordinator.start()
        }

        func advance(_ seconds: TimeInterval) {
            clock = clock.addingTimeInterval(seconds)
        }

        func beginChromecastPress() {
            coordinator.remoteAudioStarted(
                remote: .chromecast,
                reason: 0x03,
                supportsPhysicalHoldGesture: true
            )
        }

        func endChromecastPress() {
            coordinator.remoteAudioStopped(remote: .chromecast, reason: 0x02)
        }
    }

    private final class CheckContext {
        private(set) var failures = 0

        func expect(
            _ condition: @autoclosure () -> Bool,
            _ message: String
        ) {
            if condition() {
                VoiceSessionSelfTest.emit("[SELF-TEST] PASS \(message)")
            } else {
                failures += 1
                VoiceSessionSelfTest.emit("[SELF-TEST] FAIL \(message)")
            }
        }
    }

    private static func emit(_ message: String) {
        FileHandle.standardError.write(Data((message + "\n").utf8))
    }

    static func run() -> Bool {
        let checks = CheckContext()
        testActiveBeforeRelease(checks)
        testStopBeforeActive(checks)
        testSecondTapCloses(checks)
        testLongPressCloses(checks)
        testKeyboardOpenRemoteClose(checks)
        testRemoteOpenKeyboardClose(checks)
        testX6ReasonZeroOpens(checks)
        testChromecastReasonZeroWhileClosedIsIgnored(checks)
        testIndependentRemoteStops(checks)
        testDebouncedRetry(checks)
        testUnobservedToolTapToggle(checks)
        testUnobservedToolIgnoresDoubaoSnapshots(checks)
        testUnobservedToolKeyboardToggle(checks)
        emit("[SELF-TEST] completed failures=\(checks.failures)")
        return checks.failures == 0
    }

    private static func testActiveBeforeRelease(_ c: CheckContext) {
        let h = Harness()
        h.beginChromecastPress()
        h.doubao.emit(.active)
        c.expect(h.openRequests.isEmpty, "active-before-release waits for physical STOP")
        h.advance(0.18)
        h.endChromecastPress()
        c.expect(h.triggerTapCount == 1, "first short tap sends one trigger")
        c.expect(h.openRequests.count == 1, "physical STOP immediately requests persistent stream")
        c.expect(h.openRequests.first?.0 == .chromecast, "recovery targets Chromecast")
        c.expect(h.openRequests.first?.1 == true, "recovery bypasses transport debounce")
        c.expect(h.coordinator.debugSnapshot.phase == "open", "active-before-release remains open")
    }

    private static func testStopBeforeActive(_ c: CheckContext) {
        let h = Harness()
        h.beginChromecastPress()
        h.advance(0.12)
        h.endChromecastPress()
        c.expect(h.openRequests.count == 1, "stop-before-active also opens without fixed delay")
        h.doubao.emit(.active)
        c.expect(h.openRequests.count == 1, "active confirmation does not duplicate MIC_OPEN")
        c.expect(h.coordinator.debugSnapshot.phase == "open", "late active completes opening")
    }

    private static func testSecondTapCloses(_ c: CheckContext) {
        let h = Harness()
        h.beginChromecastPress()
        h.advance(0.15)
        h.endChromecastPress()
        h.doubao.emit(.active)
        h.coordinator.remoteAudioStarted(remote: .chromecast, reason: 0x00)
        h.beginChromecastPress()
        h.advance(0.16)
        h.endChromecastPress()
        c.expect(h.triggerTapCount == 2, "second short tap sends exactly one close trigger")
        c.expect(h.openRequests.count == 1, "second tap never reopens microphone")
        c.expect(h.coordinator.debugSnapshot.phase == "closing", "second tap enters closing")
    }

    private static func testLongPressCloses(_ c: CheckContext) {
        let h = Harness()
        h.beginChromecastPress()
        h.doubao.emit(.active)
        h.advance(0.70)
        h.endChromecastPress()
        c.expect(h.triggerTapCount == 2, "long release sends one close trigger")
        c.expect(h.openRequests.isEmpty, "long release never requests persistent reopen")
        c.expect(h.coordinator.debugSnapshot.phase == "closing", "long release enters closing")
    }

    private static func testKeyboardOpenRemoteClose(_ c: CheckContext) {
        let h = Harness()
        h.coordinator.triggerDownObserved(isSynthetic: false)
        h.coordinator.triggerUpObserved(isSynthetic: false)
        c.expect(h.triggerTapCount == 0, "physical keyboard open is not replayed")
        c.expect(h.openRequests.first?.0 == .chromecast, "keyboard open selects preferred remote")
        h.doubao.emit(.active)
        h.coordinator.remoteAudioStarted(remote: .chromecast, reason: 0x00)
        h.beginChromecastPress()
        h.advance(0.14)
        h.endChromecastPress()
        c.expect(h.triggerTapCount == 1, "remote can close keyboard-opened session")
        c.expect(h.coordinator.debugSnapshot.phase == "closing", "cross-close enters closing")
    }

    private static func testRemoteOpenKeyboardClose(_ c: CheckContext) {
        let h = Harness()
        h.beginChromecastPress()
        h.advance(0.16)
        h.endChromecastPress()
        h.doubao.emit(.active)
        h.coordinator.remoteAudioStarted(remote: .chromecast, reason: 0x00)
        h.coordinator.triggerDownObserved(isSynthetic: false)
        h.coordinator.triggerUpObserved(isSynthetic: false)
        h.doubao.emit(.active)
        RunLoop.current.run(until: Date().addingTimeInterval(0.22))
        c.expect(h.triggerTapCount == 1, "keyboard close does not synthesize another trigger")
        c.expect(h.openRequests.count == 1, "stale active cannot reopen transport")
        c.expect(h.coordinator.debugSnapshot.phase == "closing", "stale active keeps closing phase")
        h.doubao.emit(.inactive)
        c.expect(h.coordinator.debugSnapshot.phase == "closed", "inactive completes keyboard close")
    }

    private static func testIndependentRemoteStops(_ c: CheckContext) {
        let h = Harness()
        h.coordinator.remoteAudioStarted(remote: .x6, reason: 0x00)
        h.coordinator.remoteAudioStarted(
            remote: .chromecast,
            reason: 0x03,
            supportsPhysicalHoldGesture: true
        )
        c.expect(h.triggerTapCount == 1, "second remote start does not toggle Doubao twice")
        c.expect(
            h.coordinator.debugSnapshot.streamingRemotes == Set([.x6, .chromecast]),
            "both remote transports are tracked independently"
        )
        h.coordinator.remoteAudioStopped(remote: .x6, reason: 0x00)
        c.expect(
            h.coordinator.debugSnapshot.streamingRemotes == Set([.chromecast]),
            "one remote STOP does not erase the other"
        )
    }

    private static func testX6ReasonZeroOpens(_ c: CheckContext) {
        let h = Harness()
        h.coordinator.remoteAudioStarted(remote: .x6, reason: 0x00)
        c.expect(h.triggerTapCount == 1, "X6 physical reason-0 sends one open trigger")
        c.expect(h.coordinator.debugSnapshot.phase == "opening", "X6 reason-0 begins opening")
        c.expect(
            h.coordinator.debugSnapshot.streamingRemotes == Set([.x6]),
            "X6 reason-0 keeps its physical stream"
        )
    }

    private static func testChromecastReasonZeroWhileClosedIsIgnored(
        _ c: CheckContext
    ) {
        let h = Harness()
        h.coordinator.remoteAudioStarted(remote: .chromecast, reason: 0x00)
        c.expect(h.triggerTapCount == 0, "stale Chromecast reason-0 sends no trigger")
        c.expect(h.coordinator.debugSnapshot.phase == "closed", "stale Chromecast reason-0 stays closed")
        c.expect(
            h.coordinator.debugSnapshot.streamingRemotes.isEmpty,
            "stale Chromecast reason-0 is closed locally"
        )
    }

    // MARK: - Tools without an observable recording state (WeType, custom)

    private static func testUnobservedToolTapToggle(_ c: CheckContext) {
        let h = Harness(observesToolState: false)
        h.beginChromecastPress()
        c.expect(
            h.coordinator.debugSnapshot.phase == "open",
            "unobserved tool opens without waiting for CoreAudio"
        )
        h.advance(0.15)
        h.endChromecastPress()
        c.expect(
            h.openRequests.count == 1,
            "unobserved tool still requests a persistent stream after a tap"
        )
        h.coordinator.remoteAudioStarted(remote: .chromecast, reason: 0x00)
        h.beginChromecastPress()
        h.advance(0.15)
        h.endChromecastPress()
        c.expect(
            h.triggerIntents == [.open, .close],
            "unobserved tool receives exactly one open then one close trigger"
        )
        c.expect(
            h.coordinator.debugSnapshot.phase == "closing",
            "unobserved second tap enters closing"
        )
        RunLoop.current.run(until: Date().addingTimeInterval(1.35))
        c.expect(
            h.coordinator.debugSnapshot.phase == "closed",
            "unobserved close completes without CoreAudio confirmation"
        )
        c.expect(
            h.sessionFinishedCount == 1,
            "session-finished fires once so the input source can be restored"
        )
    }

    private static func testUnobservedToolIgnoresDoubaoSnapshots(
        _ c: CheckContext
    ) {
        let h = Harness(observesToolState: false)
        h.coordinator.remoteAudioStarted(remote: .x6, reason: 0x00)
        h.doubao.emit(.inactive)
        h.doubao.emit(.unavailable)
        c.expect(
            h.coordinator.debugSnapshot.phase == "open",
            "Doubao snapshots cannot close another tool's session"
        )
        RunLoop.current.run(until: Date().addingTimeInterval(1.15))
        c.expect(
            h.coordinator.debugSnapshot.phase == "open",
            "no opening timeout applies to an unobserved tool"
        )
        h.doubao.emit(.active)
        h.coordinator.remoteHIDShortPress()
        c.expect(
            h.triggerIntents == [.open, .close],
            "X6 HID short press closes the unobserved session once"
        )
    }

    private static func testUnobservedToolKeyboardToggle(_ c: CheckContext) {
        let h = Harness(observesToolState: false)
        h.coordinator.triggerDownObserved(isSynthetic: false)
        h.coordinator.triggerUpObserved(isSynthetic: false)
        c.expect(
            h.coordinator.debugSnapshot.phase == "open",
            "physical trigger opens an unobserved session"
        )
        c.expect(
            h.openRequests.first?.0 == .chromecast,
            "physical trigger opens the preferred remote microphone"
        )
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        h.coordinator.triggerDownObserved(isSynthetic: false)
        h.coordinator.triggerUpObserved(isSynthetic: false)
        c.expect(
            h.coordinator.debugSnapshot.phase == "closing",
            "second physical trigger closes the unobserved session"
        )
        c.expect(
            h.triggerTapCount == 0,
            "physical triggers are never replayed to an unobserved tool"
        )
    }

    private static func testDebouncedRetry(_ c: CheckContext) {
        let h = Harness()
        h.openResults = [.retryAfter(0.02), .sent]
        h.beginChromecastPress()
        h.advance(0.13)
        h.endChromecastPress()
        c.expect(h.coordinator.debugSnapshot.openRequestedRemote == nil, "debounced request is not marked sent")
        RunLoop.current.run(until: Date().addingTimeInterval(0.08))
        c.expect(h.openRequests.count == 2, "debounced open receives a bounded retry")
        c.expect(
            h.coordinator.debugSnapshot.openRequestedRemote == .chromecast,
            "only the sent retry becomes pending"
        )
    }
}
#endif
