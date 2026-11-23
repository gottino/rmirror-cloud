import XCTest
@testable import RMirrorKit

final class OnboardingCopyTests: XCTestCase {
    func testSyncButtonLabel() {
        XCTAssertEqual(OnboardingCopy.syncButton(notebooks: 1, pages: 1), "Sync 1 notebook (1 page)")
        XCTAssertEqual(OnboardingCopy.syncButton(notebooks: 3, pages: 23), "Sync 3 notebooks (23 pages)")
    }

    func testOverAllowanceMessage() {
        XCTAssertEqual(OnboardingCopy.overAllowance(remaining: 12),
                       "That's more than the 12 pages you have left this month. Untick a notebook.")
        XCTAssertEqual(OnboardingCopy.overAllowance(remaining: 1),
                       "That's more than the 1 page you have left this month. Untick a notebook.")
    }

    func testSuggestionTitleAdaptsToCount() {
        XCTAssertEqual(OnboardingCopy.suggestionTitle(count: 3), "Start with your 3 most recent notebooks")
        XCTAssertEqual(OnboardingCopy.suggestionTitle(count: 1), "Start with your most recent notebook")
    }

    func testNoTechnicalWords() throws {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "API", "Web UI", "agent"]
        let pattern = "\\b(" + banned.map(NSRegularExpression.escapedPattern(for:)).joined(separator: "|") + ")\\b"
        let regex = try NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
        for string in OnboardingCopy.allStrings {
            let range = NSRange(string.startIndex..., in: string)
            XCTAssertNil(regex.firstMatch(in: string, range: range), "Technical word in: \(string)")
        }
    }

    func testWritingRules() {
        for string in OnboardingCopy.allStrings {
            XCTAssertFalse(string.isEmpty)
            XCTAssertFalse(string.contains("!"), "Exclamation mark in: \(string)")
            XCTAssertFalse(string.contains("\u{2014}"), "Em dash in: \(string)")
        }
    }
}
