import XCTest
@testable import RMirrorKit

final class CoreDiagnosticsTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("rmirror-diagnostics-\(UUID().uuidString)")
    }

    func testEntriesGoToAPrivateFile() throws {
        let url = directory.appendingPathComponent("logs/core-failures.log")
        XCTAssertTrue(CoreDiagnostics.write("first", to: url))
        XCTAssertTrue(CoreDiagnostics.write("second", to: url))
        let text = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(text.contains("first") && text.contains("second"))
        let permissions = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber
        XCTAssertEqual(permissions?.intValue, 0o600)
        let folder = try FileManager.default.attributesOfItem(atPath: url.deletingLastPathComponent().path)[.posixPermissions] as? NSNumber
        XCTAssertEqual(folder?.intValue, 0o700)
    }

    func testFileStaysBounded() throws {
        let url = directory.appendingPathComponent("core-failures.log")
        let big = String(repeating: "x", count: 40_000)
        for _ in 0..<4 { CoreDiagnostics.write(big, to: url) }
        let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
        XCTAssertLessThanOrEqual(size?.intValue ?? .max, CoreDiagnostics.maxFileBytes)
    }
}
