// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "RMirror",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "RMirrorKit", targets: ["RMirrorKit"]),
        .executable(name: "RMirrorApp", targets: ["RMirrorApp"]),
    ],
    targets: [
        // No UI. Local API client, core supervisor, app state, user-facing copy.
        .target(name: "RMirrorKit", path: "Sources/RMirrorKit"),
        // AppKit lifecycle hosting SwiftUI views.
        .executableTarget(name: "RMirrorApp", dependencies: ["RMirrorKit"], path: "Sources/RMirrorApp"),
        .testTarget(name: "RMirrorKitTests", dependencies: ["RMirrorKit"], path: "Tests/RMirrorKitTests"),
    ],
    swiftLanguageVersions: [.v5]
)
