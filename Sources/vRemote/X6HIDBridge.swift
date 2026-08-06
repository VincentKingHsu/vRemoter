import Foundation
import IOKit.hid

private func x6DeviceMatched(
    context: UnsafeMutableRawPointer?,
    result: IOReturn,
    sender: UnsafeMutableRawPointer?,
    device: IOHIDDevice
) {
    guard let context else { return }
    Unmanaged<X6HIDBridge>
        .fromOpaque(context)
        .takeUnretainedValue()
        .deviceDidMatch(result: result, device: device)
}

private func x6DeviceRemoved(
    context: UnsafeMutableRawPointer?,
    result: IOReturn,
    sender: UnsafeMutableRawPointer?,
    device: IOHIDDevice
) {
    guard let context else { return }
    Unmanaged<X6HIDBridge>
        .fromOpaque(context)
        .takeUnretainedValue()
        .deviceDidRemove(device)
}

private func x6InputReport(
    context: UnsafeMutableRawPointer?,
    result: IOReturn,
    sender: UnsafeMutableRawPointer?,
    type: IOHIDReportType,
    reportID: UInt32,
    report: UnsafeMutablePointer<UInt8>,
    reportLength: CFIndex
) {
    guard let context, result == kIOReturnSuccess, reportLength > 0 else {
        return
    }
    let bridge = Unmanaged<X6HIDBridge>
        .fromOpaque(context)
        .takeUnretainedValue()
    bridge.handleReport(
        reportID: reportID,
        data: Data(bytes: report, count: reportLength)
    )
}

/// Read-only protocol probe for the Shenzhen Xingwei X6 BLE remote.
///
/// The device exposes normal keyboard/consumer/mouse collections plus a
/// vendor-defined 255-byte input report (ID 0x5A). We initially observe it
/// non-exclusively so ordinary buttons keep working while we identify the
/// voice-button usage and audio encoding.
final class X6HIDBridge {
    static let vendorID = 0x1D5A
    static let productID = 0xC081
    static let voiceDataReportID: UInt32 = 0x5A
    var onConnectionChanged: ((Bool) -> Void)?
    var onConsumerUsageChanged: ((UInt16) -> Void)?
    var onNativeSearchEdge: (() -> Void)?
    /// Physical Search-down. Used only to pre-arm the remote audio route.
    var onPhysicalVoiceDown: (() -> Void)?
    /// Semantic events; each physical gesture produces exactly one path.
    var onShortPress: (() -> Void)?
    var onLongPressBegan: (() -> Void)?
    var onLongPressEnded: (() -> Void)?

    private var manager: IOHIDManager?
    private var activeDevice: IOHIDDevice?
    private var lastConsumerUsage: UInt16 = 0
    private var voiceGestureActive = false
    private var longVoiceKeyActive = false
    private var longPressConfirmed = false
    private var longPressConfirmWorkItem: DispatchWorkItem?
    private var deferredVoiceRelease: DispatchWorkItem?
    private var voiceReportCount = 0
    private var voiceByteCount = 0

    func start() {
        stop()
        let manager = IOHIDManagerCreate(
            kCFAllocatorDefault,
            IOOptionBits(kIOHIDOptionsTypeNone)
        )
        IOHIDManagerSetDeviceMatching(
            manager,
            [
                kIOHIDVendorIDKey: Self.vendorID,
                kIOHIDProductIDKey: Self.productID,
            ] as CFDictionary
        )

        let context = Unmanaged.passUnretained(self).toOpaque()
        IOHIDManagerRegisterDeviceMatchingCallback(
            manager,
            x6DeviceMatched,
            context
        )
        IOHIDManagerRegisterDeviceRemovalCallback(
            manager,
            x6DeviceRemoved,
            context
        )
        IOHIDManagerRegisterInputReportCallback(
            manager,
            x6InputReport,
            context
        )
        IOHIDManagerScheduleWithRunLoop(
            manager,
            CFRunLoopGetMain(),
            CFRunLoopMode.commonModes.rawValue
        )
        let result = IOHIDManagerOpen(
            manager,
            IOOptionBits(kIOHIDOptionsTypeNone)
        )
        guard result == kIOReturnSuccess else {
            print(
                "[X6] HID manager open failed: 0x" +
                String(UInt32(bitPattern: result), radix: 16)
            )
            IOHIDManagerUnscheduleFromRunLoop(
                manager,
                CFRunLoopGetMain(),
                CFRunLoopMode.commonModes.rawValue
            )
            return
        }
        self.manager = manager
        print("[X6] HID probe started; waiting for X6-Remote")
    }

    func stop() {
        deferredVoiceRelease?.cancel()
        deferredVoiceRelease = nil
        longPressConfirmWorkItem?.cancel()
        longPressConfirmWorkItem = nil
        if voiceGestureActive {
            let wasLong = longPressConfirmed
            voiceGestureActive = false
            longVoiceKeyActive = false
            longPressConfirmed = false
            if wasLong {
                onLongPressEnded?()
            }
        }
        if let activeDevice {
            IOHIDDeviceClose(
                activeDevice,
                IOOptionBits(kIOHIDOptionsTypeNone)
            )
        }
        activeDevice = nil
        onConnectionChanged?(false)
        guard let manager else { return }
        IOHIDManagerUnscheduleFromRunLoop(
            manager,
            CFRunLoopGetMain(),
            CFRunLoopMode.commonModes.rawValue
        )
        IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        self.manager = nil
    }

    fileprivate func deviceDidMatch(
        result: IOReturn,
        device: IOHIDDevice
    ) {
        guard result == kIOReturnSuccess, activeDevice == nil else { return }
        let openResult = IOHIDDeviceOpen(
            device,
            IOOptionBits(kIOHIDOptionsTypeNone)
        )
        guard openResult == kIOReturnSuccess else {
            print(
                "[X6] device open failed: 0x" +
                String(UInt32(bitPattern: openResult), radix: 16)
            )
            return
        }
        activeDevice = device
        voiceReportCount = 0
        voiceByteCount = 0
        lastConsumerUsage = 0
        onConnectionChanged?(true)
        print(
            "[X6] connected VID=0x1d5a PID=0xc081 " +
            "manufacturer=shenzhen_xingwei"
        )
    }

    fileprivate func deviceDidRemove(_ device: IOHIDDevice) {
        guard let activeDevice, CFEqual(activeDevice, device) else { return }
        IOHIDDeviceClose(
            activeDevice,
            IOOptionBits(kIOHIDOptionsTypeNone)
        )
        self.activeDevice = nil
        lastConsumerUsage = 0
        onConnectionChanged?(false)
        print("[X6] disconnected")
    }

    fileprivate func handleReport(reportID: UInt32, data: Data) {
        // On macOS the manager callback includes the report ID as byte zero
        // for this device, even though it is also supplied separately.
        let payload: Data
        if data.first == UInt8(truncatingIfNeeded: reportID) {
            payload = Data(data.dropFirst())
        } else {
            payload = data
        }

        switch reportID {
        case 0x01:
            logSmallReport(name: "keyboard", reportID: reportID, data: payload)
            handleKeyboardReport(payload)
        case 0x02:
            handleConsumerReport(payload)
        case 0x03:
            logSmallReport(name: "system", reportID: reportID, data: payload)
        case 0x04:
            // Mouse reports are intentionally ignored to avoid log noise.
            break
        case Self.voiceDataReportID:
            handleVoiceData(payload)
        default:
            logSmallReport(name: "unknown", reportID: reportID, data: payload)
        }
    }

    private func handleConsumerReport(_ data: Data) {
        guard data.count >= 2 else { return }
        let usage = UInt16(data[data.startIndex])
            | UInt16(data[data.index(after: data.startIndex)]) << 8
        guard usage != lastConsumerUsage else { return }
        lastConsumerUsage = usage
        print(
            String(
                format: "[X6] consumer usage=0x%04X edge=%@ raw=%@",
                usage,
                usage == 0 ? "up" : "down",
                hex(data)
            )
        )
        onConsumerUsageChanged?(usage)
        if usage == 0x0221 {
            onNativeSearchEdge?()
            beginVoiceGestureIfNeeded(source: "consumer-search")
        } else if usage == 0, voiceGestureActive, !longVoiceKeyActive {
            onNativeSearchEdge?()
            // X6 releases Consumer Search just before it transitions to the
            // hold-only keyboard usage 0xAA. Delay briefly so a short press
            // ends here while a long press can cancel this release.
            scheduleDeferredVoiceRelease()
        }
    }

    private func handleKeyboardReport(_ data: Data) {
        guard data.count >= 2 else { return }
        let keys = Set(data.dropFirst(2).filter { $0 != 0 })
        let voiceHeld = keys.contains(0xAA)
        guard voiceHeld != longVoiceKeyActive else { return }
        longVoiceKeyActive = voiceHeld

        if voiceHeld {
            deferredVoiceRelease?.cancel()
            deferredVoiceRelease = nil
            beginVoiceGestureIfNeeded(source: "keyboard-0xAA")
            // Some X6 firmware emits the 0xAA keyboard usage for both a tap
            // and a hold. Do not classify it as long immediately; confirm
            // that it remains asserted for the same 280ms window used by the
            // normal HID gesture classifier.
            longPressConfirmed = false
            longPressConfirmWorkItem?.cancel()
            let work = DispatchWorkItem { [weak self] in
                guard let self,
                      self.voiceGestureActive,
                      self.longVoiceKeyActive
                else { return }
                self.longPressConfirmed = true
                self.longPressConfirmWorkItem = nil
                self.onLongPressBegan?()
                print("[X6] physical voice HOLD confirmed")
            }
            longPressConfirmWorkItem = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.28, execute: work)
        } else if voiceGestureActive {
            longPressConfirmWorkItem?.cancel()
            longPressConfirmWorkItem = nil
            if longPressConfirmed {
                finishLongGesture(source: "keyboard-0xAA")
            } else {
                finishShortGesture(source: "keyboard-0xAA")
            }
        }
    }

    private func beginVoiceGestureIfNeeded(source: String) {
        guard !voiceGestureActive else { return }
        deferredVoiceRelease?.cancel()
        deferredVoiceRelease = nil
        voiceGestureActive = true
        print("[X6] voice DOWN source=\(source)")
        onPhysicalVoiceDown?()
    }

    private func scheduleDeferredVoiceRelease() {
        deferredVoiceRelease?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.longVoiceKeyActive else { return }
            self.deferredVoiceRelease = nil
            self.finishShortGesture(source: "consumer-search")
        }
        deferredVoiceRelease = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: work)
    }

    private func finishShortGesture(source: String) {
        deferredVoiceRelease?.cancel()
        deferredVoiceRelease = nil
        guard voiceGestureActive else { return }
        voiceGestureActive = false
        longVoiceKeyActive = false
        longPressConfirmed = false
        longPressConfirmWorkItem?.cancel()
        longPressConfirmWorkItem = nil
        print("[X6] voice UP source=\(source)")
        onShortPress?()
    }

    private func finishLongGesture(source: String) {
        deferredVoiceRelease?.cancel()
        deferredVoiceRelease = nil
        guard voiceGestureActive else { return }
        voiceGestureActive = false
        longVoiceKeyActive = false
        longPressConfirmed = false
        longPressConfirmWorkItem?.cancel()
        longPressConfirmWorkItem = nil
        print("[X6] voice LONG UP source=\(source)")
        onLongPressEnded?()
    }

    private func handleVoiceData(_ data: Data) {
        voiceReportCount += 1
        voiceByteCount += data.count
        let shouldLog =
            voiceReportCount <= 6 || voiceReportCount.isMultiple(of: 100)
        guard shouldLog else { return }

        let signed = data.map { Int(Int8(bitPattern: $0)) }
        let mean = signed.isEmpty
            ? 0
            : Double(signed.reduce(0, +)) / Double(signed.count)
        let rms = signed.isEmpty
            ? 0
            : sqrt(
                signed.reduce(0.0) { $0 + Double($1 * $1) }
                    / Double(signed.count)
            )
        print(
            String(
                format:
                    "[X6] voice report=%d len=%d totalBytes=%d " +
                    "signedMean=%.2f signedRMS=%.2f unique=%d hex=%@",
                voiceReportCount,
                data.count,
                voiceByteCount,
                mean,
                rms,
                Set(data).count,
                hex(data.prefix(24))
            )
        )
    }

    private func logSmallReport(
        name: String,
        reportID: UInt32,
        data: Data
    ) {
        print(
            String(
                format: "[X6] %@ reportID=0x%02X len=%d hex=%@",
                name,
                reportID,
                data.count,
                hex(data)
            )
        )
    }

    private func hex<S: Sequence>(_ bytes: S) -> String
    where S.Element == UInt8 {
        bytes.map { String(format: "%02X", $0) }.joined(separator: " ")
    }
}
