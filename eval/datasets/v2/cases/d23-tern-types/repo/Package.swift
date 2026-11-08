// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "Tern",
    targets: [.executableTarget(name: "Tern", exclude: ["obsolete.txt"])]
)
