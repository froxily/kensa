// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "Survey", targets: [.target(name: "Survey"), .testTarget(name: "SurveyTests", dependencies: ["Survey"])])
