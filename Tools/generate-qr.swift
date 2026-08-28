import AppKit
import CoreImage
import Foundation

guard CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: generate-qr <text> <output.png>\n".utf8))
    exit(2)
}

let message = CommandLine.arguments[1]
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
guard let data = message.data(using: .utf8),
      let filter = CIFilter(name: "CIQRCodeGenerator") else {
    exit(1)
}

filter.setValue(data, forKey: "inputMessage")
filter.setValue("H", forKey: "inputCorrectionLevel")
guard let output = filter.outputImage?.transformed(by: .init(scaleX: 14, y: 14)) else {
    exit(1)
}

let context = CIContext(options: [.useSoftwareRenderer: false])
guard let cgImage = context.createCGImage(output, from: output.extent) else {
    exit(1)
}
let bitmap = NSBitmapImageRep(cgImage: cgImage)
guard let png = bitmap.representation(using: .png, properties: [:]) else {
    exit(1)
}
try png.write(to: outputURL, options: .atomic)
