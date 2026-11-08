// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "MarshCatalog",
    products: [.executable(name: "marsh-catalog", targets: ["MarshCatalog"])],
    targets: [.executableTarget(name: "MarshCatalog")]
)
