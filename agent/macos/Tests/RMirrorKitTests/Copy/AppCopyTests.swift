import XCTest
@testable import RMirrorKit

final class AppCopyTests: XCTestCase {
    func testNoSystemTerms() {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "API", "agent", "core", "Sparkle"]
        for sample in AppCopy.allStrings {
            XCTAssertFalse(sample.isEmpty)
            XCTAssertFalse(sample.contains("!"), sample)
            XCTAssertFalse(sample.contains("\u{2014}"), sample)
            for word in banned {
                let pattern = "\\b\(NSRegularExpression.escapedPattern(for: word))\\b"
                XCTAssertNil(sample.range(of: pattern, options: [.regularExpression, .caseInsensitive]),
                             "\"\(sample)\" contains \"\(word)\"")
            }
        }
    }

    func testUpdateFailureDoesNotBlameTheInternetWhenRMirrorIsNotRunning() {
        XCTAssertFalse(AppCopy.Update.checkFailedNotRunning.localizedCaseInsensitiveContains("internet"))
        XCTAssertTrue(AppCopy.Update.checkFailedOffline.localizedCaseInsensitiveContains("internet"))
    }
}
