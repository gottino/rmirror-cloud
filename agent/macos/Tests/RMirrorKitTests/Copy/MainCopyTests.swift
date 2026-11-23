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
        XCTAssertEqual(MainCopy.changeSummary(added: 2, removed: 0, pagesToUpload: 31), "2 notebooks added · 31 pages to upload")
        XCTAssertEqual(MainCopy.changeSummary(added: 0, removed: 1, pagesToUpload: 0), "1 notebook removed")
        XCTAssertEqual(MainCopy.changeSummary(added: 0, removed: 1, pagesToUpload: 9), "1 notebook removed")
        XCTAssertEqual(MainCopy.changeSummary(added: 1, removed: 2, pagesToUpload: 1), "1 notebook added · 2 removed · 1 page to upload")
        XCTAssertEqual(MainCopy.changeSummary(added: 1, removed: 0, pagesToUpload: 0), "1 notebook added")
    }

    func testSyncAgainSaysWhatItUploads() {
        XCTAssertEqual(MainCopy.syncAgainUploads(pages: 12), "Sync again uploads 12 pages.")
        XCTAssertEqual(MainCopy.syncAgainUploads(pages: nil), "Sync again uploads the whole notebook again.")
    }

    func testAllowanceBannerFollowsWhatTheCoreReports() {
        XCTAssertEqual(MainCopy.allowanceExhaustedLines(uploadsPaused: true, resetDay: "1 December"),
                       ["Uploads are paused until your pages reset on 1 December."])
        XCTAssertEqual(MainCopy.allowanceExhaustedLines(uploadsPaused: true, resetDay: nil),
                       ["Uploads are paused until your pages reset."])
        XCTAssertEqual(MainCopy.allowanceExhaustedLines(uploadsPaused: false, resetDay: "1 December"),
                       ["New pages still upload. They are turned into text after your pages reset.", "Resets 1 December"])
    }

    func testOverAllowanceAndRowLabel() {
        XCTAssertEqual(MainCopy.overAllowance(remaining: 12),
                       "That's more than the 12 pages you have left this month. The rest is turned into text after your pages reset.")
        XCTAssertEqual(MainCopy.rowAccessibilityLabel(name: "Meeting Notes", pages: 12, selected: true),
                       "Meeting Notes, 12 pages, selected")
    }
}
