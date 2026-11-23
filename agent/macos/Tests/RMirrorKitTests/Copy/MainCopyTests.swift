import XCTest
@testable import RMirrorKit

final class MainCopyTests: XCTestCase {
    func testNoStringUsesSystemTerms() {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "API", "Web UI", "agent",
                      "Initial Sync", "Save Selection"]
        XCTAssertFalse(MainCopy.allStrings.isEmpty)
        for sample in MainCopy.allStrings {
            for word in banned {
                let pattern = "\\b\(NSRegularExpression.escapedPattern(for: word))\\b"
                XCTAssertNil(sample.range(of: pattern, options: [.regularExpression, .caseInsensitive]),
                             "\"\(sample)\" contains \"\(word)\"")
            }
        }
    }

    func testWritingRules() {
        for sample in MainCopy.allStrings {
            XCTAssertFalse(sample.contains("!"), "\"\(sample)\" has an exclamation mark")
            XCTAssertFalse(sample.contains("\u{2014}"), "\"\(sample)\" has an em dash")
            XCTAssertFalse(sample.isEmpty)
        }
    }

    func testSyncIndicator() {
        XCTAssertEqual(MainCopy.syncIndicator(.complete(total: 12)), "12 of 12 pages synced")
        XCTAssertEqual(MainCopy.syncIndicator(.partly(synced: 4, total: 12)), "4 of 12 pages synced")
        XCTAssertEqual(MainCopy.syncIndicator(.notSynced(total: 12)), "Not synced yet")
        XCTAssertEqual(MainCopy.syncIndicator(.complete(total: 1)), "1 of 1 page synced")
    }

    func testChangeSummary() {
        XCTAssertEqual(MainCopy.changeSummary(added: 2, removed: 0, newPages: 31), "2 notebooks added · 31 new pages")
        XCTAssertEqual(MainCopy.changeSummary(added: 0, removed: 1, newPages: 0), "1 notebook removed")
        XCTAssertEqual(MainCopy.changeSummary(added: 1, removed: 2, newPages: 1), "1 notebook added · 2 removed · 1 new page")
        XCTAssertEqual(MainCopy.changeSummary(added: 1, removed: 0, newPages: 0), "1 notebook added")
    }

    func testOverAllowanceAndRowLabel() {
        XCTAssertEqual(MainCopy.overAllowance(remaining: 12),
                       "That's more than the 12 pages you have left this month. The rest will be transcribed after your pages reset.")
        XCTAssertEqual(MainCopy.rowAccessibilityLabel(name: "Meeting Notes", pages: 12, selected: true),
                       "Meeting Notes, 12 pages, selected")
    }
}
