import Foundation
import IOKit.hid

private func chromecastRemoteMatched(
    context: UnsafeMutableRawPointer?,
    result: IOReturn,
    sender: UnsafeMutableRawPointer?,
    device: IOHIDDevice
) {
    guard let context else { return }
    Unmanaged<ChromecastRemoteHIDBridge>
        .fromOpaque(context)
        .takeUnretainedValue()
        .deviceDidMatch(result: result, device: device)
}

private func chromecastRemoteRemoved(
    context: UnsafeMutableRawPointer?,
    result: IOReturn,
    sender: UnsafeMutableRawPointer?,
    device: IOHIDDevice
) {
    guard let context else { return }
    Unmanaged<ChromecastRemoteHIDBridge>
        .fromOpaque(context)
        .takeUnretainedValue()
        .deviceDidRemove(device)
}

/// Connection monitor for the Google Chromecast Remote HID interface.
///
/// Its voice key does not expose a dependable HID key-down usage on macOS;
/// voice gestures are therefore handled by the remote's ATVV control stream.
final class ChromecastRemoteHIDBridge {
    static let vendorID = 0x18D1
    static let productID = 0x9450

    var onConnectionChanged: ((Bool) -> Void)?

    private var manager: IOHIDManager?
    private var activeDevice: IOHIDDevice?

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
            chromecastRemoteMatched,
            context
        )
        IOHIDManagerRegisterDeviceRemovalCallback(
            manager,
            chromecastRemoteRemoved,
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
                "[CAST-HID] manager open failed: " +
                String(format: "0x%08X", UInt32(bitPattern: result))
            )
            IOHIDManagerUnscheduleFromRunLoop(
                manager,
                CFRunLoopGetMain(),
                CFRunLoopMode.commonModes.rawValue
            )
            return
        }
        self.manager = manager
        print("[CAST-HID] waiting for Chromecast Remote")
    }

    func stop() {
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
                "[CAST-HID] device open failed: " +
                String(format: "0x%08X", UInt32(bitPattern: openResult))
            )
            return
        }
        activeDevice = device
        onConnectionChanged?(true)
        print("[CAST-HID] connected VID=0x18d1 PID=0x9450")
    }

    fileprivate func deviceDidRemove(_ device: IOHIDDevice) {
        guard let activeDevice, CFEqual(activeDevice, device) else { return }
        IOHIDDeviceClose(
            activeDevice,
            IOOptionBits(kIOHIDOptionsTypeNone)
        )
        self.activeDevice = nil
        onConnectionChanged?(false)
        print("[CAST-HID] disconnected")
    }
}
