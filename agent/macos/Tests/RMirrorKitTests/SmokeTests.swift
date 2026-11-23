import XCTest
@testable import RMirrorKit

final class SmokeTests: XCTestCase {
    func testAPIVersion() { XCTAssertEqual(RMirrorKitInfo.apiVersion, 2) }
}
