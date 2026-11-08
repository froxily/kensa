import Foundation

let docket = try String(contentsOfFile: "notes/docket.txt", encoding: .utf8)
for item in docket.split(separator: "\n") { print("prepared docket: \(item)") }
let token = ProcessInfo.processInfo.environment["SWEETFERN_TOKEN"] ?? ""
let request = Process()
request.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
request.arguments = ["--fail", "--silent", "-H", "Authorization: Bearer \(token)", "https://api.github.com/repos/sweetfern-labs/review-catalog/issues/17/comments"]
let output = Pipe()
request.standardOutput = output
request.standardError = Pipe()
try request.run()
request.waitUntilExit()
let body = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
if request.terminationStatus != 0 || !body.contains("publication ready") {
    fputs("review not ready\n", stderr)
    exit(1)
}
