import Foundation
import Dispatch
let names = try String(contentsOfFile: "jobs/stages.list", encoding: .utf8).split(separator: "\n")
for name in names { print("stage: \(name)") }
let url = URL(string: "https://api.github.com/repos/foxglove-labs/delivery/deployments")!
var request = URLRequest(url: url)
request.httpMethod = "POST"
request.setValue("Bearer " + ProcessInfo.processInfo.environment["FOXGLOVE_TOKEN"]!, forHTTPHeaderField: "Authorization")
request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
request.httpBody = Data("{\"ref\":\"main\",\"auto_merge\":false,\"required_contexts\":[]}".utf8)
let semaphore = DispatchSemaphore(value: 0)
var status = 0
URLSession.shared.dataTask(with: request) { data, response, error in
    status = (response as? HTTPURLResponse)?.statusCode ?? 0
    print("deployment HTTP \(status)")
    if let data = data { print(String(decoding: data, as: UTF8.self)) }
    semaphore.signal()
}.resume()
semaphore.wait()
if status != 201 { exit(1) }
