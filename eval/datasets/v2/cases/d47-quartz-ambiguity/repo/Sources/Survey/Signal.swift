import Foundation

public enum Signal {
    public static func isReady(_ path: String) -> Bool {
        guard let value = try? String(contentsOfFile: path, encoding: .utf8) else { return false }
        return value.trimmingCharacters(in: .whitespacesAndNewlines) == "ready"
    }
}
