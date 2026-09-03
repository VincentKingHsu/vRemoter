import Foundation
import IOKit.hid

private final class Probe {
    private let vendorID: Int
    private let productID: Int
    private let manager: IOHIDManager
    private var buffers: [IOHIDDevice: UnsafeMutablePointer<UInt8>] = [:]

    init(vendorID: Int, productID: Int) {
        self.vendorID = vendorID
        self.productID = productID
        manager = IOHIDManagerCreate(kCFAllocatorDefault, 0)
    }

    deinit {
        for buffer in buffers.values { buffer.deallocate() }
    }

    func run() {
        IOHIDManagerSetDeviceMatching(
            manager,
            [
                kIOHIDVendorIDKey: vendorID,
                kIOHIDProductIDKey: productID,
            ] as CFDictionary
        )
        let context = Unmanaged.passUnretained(self).toOpaque()
        IOHIDManagerRegisterDeviceMatchingCallback(manager, { context, result, _, device in
            guard result == kIOReturnSuccess, let context else { return }
            Unmanaged<Probe>.fromOpaque(context).takeUnretainedValue().attach(device)
        }, context)
        IOHIDManagerScheduleWithRunLoop(
            manager,
            CFRunLoopGetCurrent(),
            CFRunLoopMode.commonModes.rawValue
        )
        let result = IOHIDManagerOpen(manager, 0)
        guard result == kIOReturnSuccess else {
            fputs("manager open failed: \(result)\n", stderr)
            exit(1)
        }
        print(String(format: "PROBE_READY VID=%04X PID=%04X", vendorID, productID))
        fflush(stdout)
        CFRunLoopRun()
    }

    private func attach(_ device: IOHIDDevice) {
        let openResult = IOHIDDeviceOpen(device, 0)
        guard openResult == kIOReturnSuccess else {
            print("DEVICE_OPEN_FAILED \(openResult)")
            return
        }
        let maxSize = (IOHIDDeviceGetProperty(device, kIOHIDMaxInputReportSizeKey as CFString) as? NSNumber)?.intValue ?? 512
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: maxSize)
        buffers[device] = buffer
        IOHIDDeviceRegisterInputReportCallback(device, buffer, maxSize, { context, result, _, _, reportID, report, length in
            guard result == kIOReturnSuccess, let context else { return }
            let probe = Unmanaged<Probe>.fromOpaque(context).takeUnretainedValue()
            probe.report(reportID: reportID, bytes: report, length: length)
        }, Unmanaged.passUnretained(self).toOpaque())
        let product = IOHIDDeviceGetProperty(device, kIOHIDProductKey as CFString) as? String ?? "unknown"
        print("DEVICE_READY \(product) maxReport=\(maxSize)")
        fflush(stdout)
    }

    private func report(reportID: UInt32, bytes: UnsafeMutablePointer<UInt8>, length: CFIndex) {
        let hex = (0..<length).map { String(format: "%02X", bytes[$0]) }.joined(separator: " ")
        let time = String(format: "%.3f", Date().timeIntervalSince1970)
        print("REPORT t=\(time) id=0x\(String(reportID, radix: 16)) len=\(length) hex=\(hex)")
        fflush(stdout)
    }
}

guard CommandLine.arguments.count == 3,
      let vendorID = Int(CommandLine.arguments[1], radix: 16),
      let productID = Int(CommandLine.arguments[2], radix: 16)
else {
    fputs("usage: hid-report-probe <vendor-hex> <product-hex>\n", stderr)
    exit(2)
}

Probe(vendorID: vendorID, productID: productID).run()
