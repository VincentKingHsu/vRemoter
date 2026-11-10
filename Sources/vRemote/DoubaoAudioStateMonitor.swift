import AppKit
import CoreAudio
import Foundation

/// Reads the input-method's real CoreAudio capture state.
///
/// This is deliberately independent from the remote-button state machine.
/// `kAudioProcessPropertyIsRunningInput` is the source of truth for whether
/// Doubao is currently recording, and `kAudioProcessPropertyDevices` tells us
/// which input device it actually opened.
final class DoubaoAudioStateMonitor {
    enum State: String {
        case unavailable
        case inactive
        case active
    }

    struct Snapshot: Equatable {
        let state: State
        let pid: pid_t?
        let processObjectID: AudioObjectID?
        let inputDeviceIDs: [AudioDeviceID]
        let inputDeviceNames: [String]

        var isRecording: Bool { state == .active }

        var deviceSummary: String {
            inputDeviceNames.isEmpty
                ? "无"
                : inputDeviceNames.joined(separator: "、")
        }
    }

    private static let targetDeviceName = "vRemoteDr 2ch"

    /// One CoreAudio process object per monitored input-method bundle ID.
    private struct Binding {
        let pid: pid_t
        let objectID: AudioObjectID
    }

    private var started = false
    private var bindings = [String: Binding]()
    private var monitoredBundleIDs = [String]()
    private var lastSnapshot: Snapshot?

    /// Bundle ID of the input method that produced the current snapshot, when
    /// one is bound. Used for diagnostics and for the status line.
    private(set) var activeHostBundleID: String?

    var activeHostTitle: String? {
        activeHostBundleID.flatMap(VoiceInputHost.title(forBundleID:))
    }

    var onSnapshotChanged: ((Snapshot) -> Void)?

    private lazy var processListListener: AudioObjectPropertyListenerBlock = {
        [weak self] _, _ in
        DispatchQueue.main.async {
            self?.refreshBindingAndPublish(force: false)
        }
    }

    private lazy var inputStateListener: AudioObjectPropertyListenerBlock = {
        [weak self] _, _ in
        DispatchQueue.main.async {
            self?.publishCurrentSnapshot(force: false)
        }
    }

    func start() {
        guard !started else { return }
        started = true

        var address = Self.processListAddress
        let status = AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            .main,
            processListListener
        )
        if status != noErr {
            print("[DOUBAO-STATE] 无法监听音频进程列表: \(Self.describe(status))")
        }
        refreshBindingAndPublish(force: true)
    }

    func stop() {
        guard started else { return }
        started = false
        unbindAll()

        var address = Self.processListAddress
        AudioObjectRemovePropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            .main,
            processListListener
        )
        lastSnapshot = nil
    }

    /// Synchronous pre-event snapshot. The trigger event tap calls this before
    /// the key event reaches the input method, so the returned value is the old
    /// state that the trigger press is about to toggle.
    func snapshotNow() -> Snapshot {
        refreshBindingsIfNeeded()
        return readCurrentSnapshot()
    }

    private func refreshBindingAndPublish(force: Bool) {
        refreshBindingsIfNeeded()
        publishCurrentSnapshot(force: force)
    }

    private func refreshBindingsIfNeeded() {
        let wanted = AppStorage.voiceInputHost.bundleIDs
        if wanted != monitoredBundleIDs {
            print("[DOUBAO-STATE] 监听目标变更 \(monitoredBundleIDs) → \(wanted)")
            unbindAll()
            monitoredBundleIDs = wanted
        }

        var live = Set<String>()
        for bundleID in monitoredBundleIDs {
            guard let app = NSRunningApplication.runningApplications(
                withBundleIdentifier: bundleID
            ).first(where: { !$0.isTerminated }) else { continue }

            let pid = app.processIdentifier
            let objectID = Self.processObject(for: pid)
            guard objectID != kAudioObjectUnknown else { continue }

            live.insert(bundleID)
            if let existing = bindings[bundleID] {
                if existing.objectID == objectID { continue }
                removeListeners(for: existing.objectID)
            }
            addListeners(for: objectID)
            bindings[bundleID] = Binding(pid: pid, objectID: objectID)
            print(
                "[DOUBAO-STATE] 已绑定 \(bundleID) pid=\(pid) " +
                "audioProcess=\(objectID)"
            )
        }

        for (bundleID, binding) in bindings where !live.contains(bundleID) {
            removeListeners(for: binding.objectID)
            bindings.removeValue(forKey: bundleID)
            print("[DOUBAO-STATE] 已解绑 \(bundleID)")
        }
    }

    private func addListeners(for objectID: AudioObjectID) {
        var runningAddress = Self.runningInputAddress
        let runningStatus = AudioObjectAddPropertyListenerBlock(
            objectID,
            &runningAddress,
            .main,
            inputStateListener
        )

        var devicesAddress = Self.inputDevicesAddress
        let devicesStatus = AudioObjectAddPropertyListenerBlock(
            objectID,
            &devicesAddress,
            .main,
            inputStateListener
        )

        if runningStatus != noErr || devicesStatus != noErr {
            print(
                "[DOUBAO-STATE] 监听注册异常 " +
                "\(Self.describe(runningStatus))/\(Self.describe(devicesStatus))"
            )
        }
    }

    private func removeListeners(for objectID: AudioObjectID) {
        var runningAddress = Self.runningInputAddress
        AudioObjectRemovePropertyListenerBlock(
            objectID,
            &runningAddress,
            .main,
            inputStateListener
        )
        var devicesAddress = Self.inputDevicesAddress
        AudioObjectRemovePropertyListenerBlock(
            objectID,
            &devicesAddress,
            .main,
            inputStateListener
        )
    }

    private func unbindAll() {
        for binding in bindings.values {
            removeListeners(for: binding.objectID)
        }
        bindings.removeAll()
        activeHostBundleID = nil
    }

    private func publishCurrentSnapshot(force: Bool) {
        guard started else { return }
        let snapshot = readCurrentSnapshot()
        guard force || snapshot != lastSnapshot else { return }
        lastSnapshot = snapshot
        print(
            "[DOUBAO-STATE] state=\(snapshot.state.rawValue) " +
            "pid=\(snapshot.pid.map(String.init) ?? "-") " +
            "devices=\(snapshot.deviceSummary)"
        )
        if snapshot.isRecording,
           !snapshot.inputDeviceNames.contains(Self.targetDeviceName)
        {
            print(
                "[DOUBAO-STATE] 警告：\(activeHostTitle ?? "输入法")正在录音，" +
                "但实际输入不是 \(Self.targetDeviceName)"
            )
        }
        onSnapshotChanged?(snapshot)
    }

    private func readCurrentSnapshot() -> Snapshot {
        guard !bindings.isEmpty else {
            activeHostBundleID = nil
            return emptySnapshot(state: .unavailable)
        }

        // Adopt whichever host is genuinely recording. Iterating in configured
        // order keeps the choice stable when several hosts are merely idle.
        var idle: (String, Binding, [AudioDeviceID])?
        for bundleID in monitoredBundleIDs {
            guard let binding = bindings[bundleID] else { continue }
            guard let running = Self.uint32Property(
                object: binding.objectID,
                selector: kAudioProcessPropertyIsRunningInput,
                scope: kAudioObjectPropertyScopeGlobal
            ) else { continue }

            let deviceIDs = Self.objectListProperty(
                object: binding.objectID,
                selector: kAudioProcessPropertyDevices,
                scope: kAudioObjectPropertyScopeInput
            )

            if running != 0 {
                activeHostBundleID = bundleID
                return Snapshot(
                    state: .active,
                    pid: binding.pid,
                    processObjectID: binding.objectID,
                    inputDeviceIDs: deviceIDs,
                    inputDeviceNames: deviceIDs.map(Self.deviceName)
                )
            }
            if idle == nil { idle = (bundleID, binding, deviceIDs) }
        }

        guard let (bundleID, binding, deviceIDs) = idle else {
            activeHostBundleID = nil
            return emptySnapshot(state: .unavailable)
        }

        activeHostBundleID = bundleID
        return Snapshot(
            state: .inactive,
            pid: binding.pid,
            processObjectID: binding.objectID,
            inputDeviceIDs: deviceIDs,
            inputDeviceNames: deviceIDs.map(Self.deviceName)
        )
    }

    private func emptySnapshot(state: State) -> Snapshot {
        Snapshot(
            state: state,
            pid: nil,
            processObjectID: nil,
            inputDeviceIDs: [],
            inputDeviceNames: []
        )
    }

    private static func processObject(for pid: pid_t) -> AudioObjectID {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var qualifier = pid
        var result = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = withUnsafePointer(to: &qualifier) { qualifierPointer in
            AudioObjectGetPropertyData(
                AudioObjectID(kAudioObjectSystemObject),
                &address,
                UInt32(MemoryLayout<pid_t>.size),
                qualifierPointer,
                &size,
                &result
            )
        }
        return status == noErr ? result : AudioObjectID(kAudioObjectUnknown)
    }

    private static func uint32Property(
        object: AudioObjectID,
        selector: AudioObjectPropertySelector,
        scope: AudioObjectPropertyScope
    ) -> UInt32? {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: scope,
            mElement: kAudioObjectPropertyElementMain
        )
        var value: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        let status = AudioObjectGetPropertyData(
            object,
            &address,
            0,
            nil,
            &size,
            &value
        )
        return status == noErr ? value : nil
    }

    private static func objectListProperty(
        object: AudioObjectID,
        selector: AudioObjectPropertySelector,
        scope: AudioObjectPropertyScope
    ) -> [AudioObjectID] {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: scope,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(
            object,
            &address,
            0,
            nil,
            &size
        ) == noErr, size > 0 else { return [] }

        var values = [AudioObjectID](
            repeating: 0,
            count: Int(size) / MemoryLayout<AudioObjectID>.size
        )
        guard AudioObjectGetPropertyData(
            object,
            &address,
            0,
            nil,
            &size,
            &values
        ) == noErr else { return [] }
        return values
    }

    private static func deviceName(_ deviceID: AudioDeviceID) -> String {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioObjectPropertyName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var value: CFString = "未知设备" as CFString
        var size = UInt32(MemoryLayout<CFString>.size)
        let status = withUnsafeMutablePointer(to: &value) { pointer in
            AudioObjectGetPropertyData(
                deviceID,
                &address,
                0,
                nil,
                &size,
                pointer
            )
        }
        return status == noErr ? value as String : "设备 \(deviceID)"
    }

    private static func describe(_ status: OSStatus) -> String {
        status == noErr ? "OK" : String(status)
    }

    private static var processListAddress: AudioObjectPropertyAddress {
        AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyProcessObjectList,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
    }

    private static var runningInputAddress: AudioObjectPropertyAddress {
        AudioObjectPropertyAddress(
            mSelector: kAudioProcessPropertyIsRunningInput,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
    }

    private static var inputDevicesAddress: AudioObjectPropertyAddress {
        AudioObjectPropertyAddress(
            mSelector: kAudioProcessPropertyDevices,
            mScope: kAudioObjectPropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
    }
}
