import XCTest
@testable import RMirrorKit

final class SafeURLTests: XCTestCase {
    func testHTTPSIsAllowedAnywhere() {
        XCTAssertNotNil(SafeURL.browserURL(from: "https://rmirror.io/dashboard"))
        XCTAssertNotNil(SafeURL.browserURL(from: " HTTPS://Example.com/path?x=1 "))
    }

    func testPlainHTTPOnlyToThisMac() {
        XCTAssertNotNil(SafeURL.browserURL(from: "http://127.0.0.1:5555/auth/bridge?ticket=x"))
        XCTAssertNotNil(SafeURL.browserURL(from: "http://localhost:3000/dashboard"))
        XCTAssertNotNil(SafeURL.browserURL(from: "http://LOCALHOST"))
        XCTAssertNotNil(SafeURL.browserURL(from: "http://[::1]:8000/api/v1"))
        XCTAssertNil(SafeURL.browserURL(from: "http://rmirror.io/dashboard"))
        XCTAssertNil(SafeURL.browserURL(from: "http://127.0.0.2"))
        XCTAssertNil(SafeURL.browserURL(from: "http://localhost.evil.com"))
    }

    func testOtherSchemesAreRefused() {
        XCTAssertNil(SafeURL.browserURL(from: "file:///etc/passwd"))
        XCTAssertNil(SafeURL.browserURL(from: "rmirror://signed-in"))
        XCTAssertNil(SafeURL.browserURL(from: "javascript:alert(1)"))
        XCTAssertNil(SafeURL.browserURL(from: "x-apple.systempreferences:com.apple.settings"))
        XCTAssertNil(SafeURL.browserURL(from: "ftp://example.com"))
        XCTAssertNil(SafeURL.browserURL(from: "https://"))
        XCTAssertNil(SafeURL.browserURL(from: "example.com"))
        XCTAssertNil(SafeURL.browserURL(from: ""))
        XCTAssertNil(SafeURL.browserURL(from: nil))
    }

    func testDashboardURL() {
        XCTAssertEqual(SafeURL.dashboardURL(base: "https://rmirror.io")?.absoluteString, "https://rmirror.io/dashboard")
        XCTAssertEqual(SafeURL.dashboardURL(base: "https://rmirror.io//")?.absoluteString, "https://rmirror.io/dashboard")
        XCTAssertEqual(SafeURL.dashboardURL(base: "http://localhost:3000")?.absoluteString, "http://localhost:3000/dashboard")
        XCTAssertNil(SafeURL.dashboardURL(base: "http://evil.example"))
        XCTAssertNil(SafeURL.dashboardURL(base: "file:///tmp"))
        XCTAssertNil(SafeURL.dashboardURL(base: ""))
        XCTAssertNil(SafeURL.dashboardURL(base: nil))
    }

    func testServerRuleMatchesTheCore() {
        XCTAssertTrue(SafeURL.isAllowedServerURL("https://rmirror.example.com/api/v1"))
        XCTAssertTrue(SafeURL.isAllowedServerURL("http://localhost:8000/api/v1"))
        XCTAssertFalse(SafeURL.isAllowedServerURL("http://rmirror.example.com/api/v1"))
    }
}
