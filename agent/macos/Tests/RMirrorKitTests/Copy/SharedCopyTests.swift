import XCTest
@testable import RMirrorKit

final class SharedCopyTests: XCTestCase {
    private func counts(uploaded: Int = 0, failed: Int = 0, leftOut: Int = 0, retry: Int = 0, total: Int? = nil) -> SyncCounts {
        SyncCounts(uploaded: uploaded, failed: failed, leftOutByPageLimit: leftOut, willRetry: retry,
                   notebooksDone: 1, notebooksTotal: 3, pagesTotal: total)
    }

    private func progress(_ outcome: SyncOutcome?, _ counts: SyncCounts) -> SyncProgress {
        SyncProgress(state: .done, outcome: outcome, counts: counts, startedAt: nil, finishedAt: nil)
    }

    func testProgressLine() {
        XCTAssertEqual(SharedCopy.progressLine(counts(uploaded: 4, total: 23)), "4 of 23 pages uploaded")
        XCTAssertEqual(SharedCopy.progressLine(counts(uploaded: 1)), "1 page uploaded")
        XCTAssertEqual(SharedCopy.notebookProgressLine(counts()), "Notebook 2 of 3")
        XCTAssertEqual(SharedCopy.progressFraction(counts(uploaded: 10, failed: 1, retry: 1, total: 24)), 0.5)
        XCTAssertNil(SharedCopy.progressFraction(counts(uploaded: 10)))
    }

    func testResultDetailsUsePlainLanguage() {
        let lines = SharedCopy.resultDetails(progress(.partial, counts(uploaded: 20, failed: 5, leftOut: 12, retry: 3)))
        XCTAssertEqual(lines, [
            "20 pages uploaded.",
            "3 pages will upload shortly. You don't need to do anything.",
            "5 pages could not be uploaded. Try again.",
            "12 pages left out because of your page limit. Older pages are skipped first.",
        ])
        XCTAssertTrue(SharedCopy.resultOffersRetry(progress(.partial, counts())))
        XCTAssertFalse(SharedCopy.resultOffersRetry(progress(.success, counts())))
    }

    func testNoUserFacingStringUsesSystemTerms() {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "API"]
        var samples: [String] = []
        for outcome in [SyncOutcome.success, .partial, .stoppedQuota, .stoppedSignIn, .failed] {
            let value = progress(outcome, counts(uploaded: 2, failed: 1, leftOut: 1, retry: 1, total: 5))
            samples.append(SharedCopy.resultTitle(value))
            samples += SharedCopy.resultDetails(value)
            samples += SharedCopy.resultDetails(progress(outcome, counts()))
        }
        for problem in [ActionProblem.coreUnreachable, .notSignedIn, .syncAlreadyRunning, .cloudUnavailable, .other] {
            samples.append(SharedCopy.problem(problem))
        }
        let states: [(Stage, AppState?)] = [
            (.starting, nil), (.coreProblem(.portInUse), nil), (.coreProblem(.readyTimeout), nil),
            (.signIn(reason: .expired), nil), (.signIn(reason: .signedOut), nil), (.remarkableMissing, nil),
            (.permission, nil), (.firstSync, nil), (.ready, Fixtures.readyState),
            (.ready, Fixtures.quotaExhaustedState), (.firstSyncProgress, Fixtures.firstSyncRunningState),
        ]
        samples += states.map { SharedCopy.statusLine(stage: $0.0, state: $0.1) }
        for sample in samples {
            for word in banned {
                let pattern = "\\b\(NSRegularExpression.escapedPattern(for: word))\\b"
                XCTAssertNil(sample.range(of: pattern, options: [.regularExpression, .caseInsensitive]),
                             "\"\(sample)\" contains \"\(word)\"")
            }
        }
    }

    func testAllowance() {
        let quota = QuotaInfo(used: 4, limit: 200, remaining: 196, resetAt: nil, fetchedAt: nil)
        XCTAssertEqual(SharedCopy.allowance(quota), "196 of 200 pages left this month")
        XCTAssertEqual(SharedCopy.allowance(QuotaInfo(used: 9, limit: -1, remaining: nil, resetAt: nil, fetchedAt: nil)), "Unlimited pages")
        XCTAssertEqual(SharedCopy.allowanceUse(pages: 23, remaining: 196), "Uses 23 of your 196 remaining pages this month")
        XCTAssertEqual(SharedCopy.allowanceUse(pages: 1, remaining: nil), "Uses 1 page")
    }

    func testStatusLine() {
        XCTAssertEqual(SharedCopy.statusLine(stage: .firstSyncProgress, state: Fixtures.firstSyncRunningState), "Syncing: 4 of 23 pages uploaded")
        XCTAssertEqual(SharedCopy.statusLine(stage: .permission, state: nil), "Needs permission to read your notebooks")
    }
}
