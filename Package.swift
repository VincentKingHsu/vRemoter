// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "vRemote",
    platforms: [.macOS(.v12)],
    targets: [
        .executableTarget(
            name: "vRemote",
            path: "Sources/vRemote"
        )
    ]
)
