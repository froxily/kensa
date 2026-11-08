import Foundation
import XCTest
@testable import Survey

final class SignalTests: XCTestCase {
    func testCount() { XCTAssertEqual("ab".count, 2) }
    func testEmpty() { XCTAssertTrue("".isEmpty) }
    func testLowercase() { XCTAssertEqual("A".lowercased(), "a") }
    func testPrefix() { XCTAssertTrue("survey".hasPrefix("sur")) }
    func testReplace() { XCTAssertEqual("a-b".replacingOccurrences(of: "-", with: "_"), "a_b") }
    func testSignal() {
        let path = ProcessInfo.processInfo.environment["SURVEY_SIGNAL_FILE"] ?? ""
        XCTAssertTrue(Signal.isReady(path))
    }
    func testSplit() { XCTAssertEqual("a,b".split(separator: ",").count, 2) }
    func testSuffix() { XCTAssertTrue("survey".hasSuffix("ey")) }
    func testUppercase() { XCTAssertEqual("b".uppercased(), "B") }
}
