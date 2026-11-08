import Foundation
import Glibc

let content = try String(contentsOfFile: "data/labels.txt", encoding: .utf8)
let labels = content.split(whereSeparator: \.isNewline)
for label in labels {
    print("prepared \(label)")
    fflush(stdout)
}
guard let endpoint = ProcessInfo.processInfo.environment["PLOVER_ENDPOINT"], !endpoint.isEmpty else {
    FileHandle.standardError.write(Data("PLOVER_ENDPOINT is not set\n".utf8))
    exit(1)
}
print("endpoint: \(endpoint), labels: \(labels.count)")
