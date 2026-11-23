import XCTest
@testable import RMirrorKit

final class SettingsCopyTests: XCTestCase {
    private func containsWord(_ word: String, in text: String) -> Bool {
        let pattern = "\\b" + NSRegularExpression.escapedPattern(for: word) + "\\b"
        return text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
    }

    func testNoSystemTermsAnywhere() {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "password"]
        for original in SettingsCopy.allStrings {
            // "log in" is the verb (required wording), not the noun "log".
            let text = original.replacingOccurrences(of: "log in", with: "", options: .caseInsensitive)
            for word in banned { XCTAssertFalse(containsWord(word, in: text), "\"\(original)\" contains \(word)") }
        }
    }

    func testAPIOnlyInDeveloperOptions() {
        for text in SettingsCopy.generalStrings { XCTAssertFalse(containsWord("API", in: text), text) }
    }

    func testStyle() {
        for text in SettingsCopy.allStrings {
            XCTAssertFalse(text.contains("!"), text)
            XCTAssertFalse(text.contains("\u{2014}"), text)
        }
    }

    func testServerURLValidation() {
        XCTAssertTrue(SettingsCopy.isValidServerURL("https://rmirror.example.com/api/v1"))
        XCTAssertTrue(SettingsCopy.isValidServerURL(" http://localhost:8000 "))
        XCTAssertTrue(SettingsCopy.isValidServerURL("http://127.0.0.1:8000/api/v1"))
        XCTAssertTrue(SettingsCopy.isValidServerURL("http://[::1]:8000/api/v1"))
        XCTAssertFalse(SettingsCopy.isValidServerURL("http://rmirror.example.com/api/v1"))
        XCTAssertFalse(SettingsCopy.isValidServerURL("file:///tmp/api"))
        XCTAssertFalse(SettingsCopy.isValidServerURL("ftp://example.com"))
        XCTAssertFalse(SettingsCopy.isValidServerURL("example.com"))
        XCTAssertFalse(SettingsCopy.isValidServerURL(""))
        XCTAssertFalse(SettingsCopy.isValidServerURL("https://"))
    }
}
