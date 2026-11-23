import XCTest
@testable import RMirrorKit

/// First contact with a server or account: the starting screen while the core asks the server what it
/// has, and the "already online but not ticked" notice afterwards.
final class CatchUpStageTests: XCTestCase {
    private let running = CoreStatus.running(CoreConnection(port: 5555, appToken: "t"))

    private func with(_ base: AppState, _ catchUp: CatchUpState, unselected: Int = 0) -> AppState {
        var state = base
        state.catchUp = CatchUpInfo(state: catchUp, unselectedOnServer: unselected)
        return state
    }

    private func stage(_ state: AppState, guided: Bool = false) -> Stage {
        Stage.derive(core: running, state: state, guidedSyncActive: guided)
    }

    func testPendingWhileSignedInWithAReadableFolderIsStarting() {
        // first_sync reads false while pending: neither the first sync nor the main window shows.
        XCTAssertEqual(stage(Fixtures.catchingUpState), .starting)
        XCTAssertEqual(stage(with(Fixtures.firstSyncPendingState, .pending)), .starting)
        XCTAssertEqual(stage(with(Fixtures.readyState, .pending)), .starting)
        // Offline with a stored sign-in counts as signed in, as everywhere else.
        XCTAssertEqual(stage(with(Fixtures.offlineState, .pending)), .starting)
        XCTAssertTrue(Stage.isCatchingUp(Fixtures.catchingUpState))
    }

    func testOtherCatchUpStatesFollowTheUsualRules() {
        for value in [CatchUpState.done, .unavailable, .notNeeded] {
            XCTAssertEqual(stage(with(Fixtures.firstSyncPendingState, value)), .firstSync, "\(value)")
            XCTAssertEqual(stage(with(Fixtures.readyState, value)), .ready, "\(value)")
            XCTAssertEqual(stage(with(Fixtures.offlineState, value)), .ready, "\(value)")
            XCTAssertEqual(stage(with(Fixtures.firstSyncRunningState, value), guided: true), .firstSyncProgress, "\(value)")
            XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.readyState, value)))
        }
    }

    func testSignInAndFolderStagesKeepTheirPrecedence() {
        // The core reads pending while signed out or while the folder cannot be read: never evaluated then.
        XCTAssertEqual(stage(with(Fixtures.signedOutState, .pending)), .signIn(reason: .signedOut))
        XCTAssertEqual(stage(with(Fixtures.signInRequiredState, .pending)), .signIn(reason: .expired))
        XCTAssertEqual(stage(with(Fixtures.folderMissingState, .pending)), .remarkableMissing)
        XCTAssertEqual(stage(with(Fixtures.folderUnreadableState, .pending)), .permission)
        XCTAssertEqual(stage(with(Fixtures.checkingSignInState, .pending)), .starting)
        XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.signedOutState, .pending)))
        XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.signInRequiredState, .pending)))
        XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.checkingSignInState, .pending)))
        XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.folderMissingState, .pending)))
        XCTAssertFalse(Stage.isCatchingUp(with(Fixtures.folderUnreadableState, .pending)))
        XCTAssertFalse(Stage.isCatchingUp(nil))
        // A core failure or a core not running yet still wins.
        XCTAssertEqual(Stage.derive(core: .failed(.portInUse), state: Fixtures.catchingUpState, guidedSyncActive: false),
                       .coreProblem(.portInUse))
    }

    func testStatusLineSaysWhatIsHappening() {
        XCTAssertEqual(SharedCopy.statusLine(stage: .starting, state: Fixtures.catchingUpState), "Checking what's already online…")
        XCTAssertEqual(SharedCopy.statusLine(stage: .starting, state: with(Fixtures.offlineState, .pending)),
                       "Waiting for an internet connection")
        XCTAssertEqual(SharedCopy.statusLine(stage: .starting, state: nil), "Starting…")
        XCTAssertEqual(SharedCopy.statusLine(stage: .starting, state: Fixtures.checkingSignInState), "Starting…")
    }

    func testOnServerNotTickedFollowsTheDraft() {
        let notebooks = Fixtures.catchUpLibraryNotebooks.notebooks
        let saved = NotebookList.savedSelection(notebooks)
        XCTAssertEqual(NotebookList.onServerNotTicked(notebooks, draft: saved),
                       ["nb-roadmap", "nb-quarterly", "nb-standup", "nb-recipes"])
        // Ticked by hand already: left as it is. Unticked by hand: ticked again.
        var draft = saved.union(["nb-standup"])
        draft.remove("nb-budget")
        XCTAssertEqual(NotebookList.onServerNotTicked(notebooks, draft: draft),
                       ["nb-roadmap", "nb-quarterly", "nb-recipes", "nb-budget"])
        // Nothing known about the server: nothing to tick.
        XCTAssertEqual(NotebookList.onServerNotTicked(Fixtures.libraryNotebooks.notebooks, draft: []), [])
    }

    func testTickingThemCountsOnlyWhatIsNotOnline() {
        let notebooks = Fixtures.catchUpLibraryNotebooks.notebooks
        let saved = NotebookList.savedSelection(notebooks)
        let draft = saved.union(NotebookList.onServerNotTicked(notebooks, draft: saved))
        let diff = NotebookList.diff(notebooks, saved: saved, draft: draft)
        XCTAssertEqual(diff.added.count, 4)
        // Standup has 5 pages changed since; the other three are online in full.
        XCTAssertEqual(diff.newPages, 5)
    }
}

final class CatchUpCopyTests: XCTestCase {
    func testNoticeSingularAndPlural() {
        XCTAssertEqual(MainCopy.selectionNoticeTitle(count: 12),
                       "12 notebooks from this account are already online but not ticked on this Mac.")
        XCTAssertEqual(MainCopy.selectionNoticeTitle(count: 1),
                       "1 notebook from this account is already online but not ticked on this Mac.")
        XCTAssertEqual(MainCopy.selectionNoticeBody(count: 12), "Ticking them only uploads what is new or changed.")
        XCTAssertEqual(MainCopy.selectionNoticeBody(count: 1), "Ticking it only uploads what is new or changed.")
        XCTAssertEqual(MainCopy.tickThem(count: 12), "Tick them")
        XCTAssertEqual(MainCopy.tickThem(count: 1), "Tick it")
        XCTAssertEqual(MainCopy.notNow, "Not now")
    }

    func testNewWordingIsPlain() {
        let banned = ["token", "rate limit", "callback", "log", "queue", "quota", "OCR", "API", "catch-up", "catch up",
                      "server", "manifest", "sync records"]
        let samples = [
            MainCopy.selectionNoticeTitle(count: 1), MainCopy.selectionNoticeTitle(count: 12),
            MainCopy.selectionNoticeBody(count: 1), MainCopy.selectionNoticeBody(count: 12),
            MainCopy.tickThem(count: 1), MainCopy.tickThem(count: 12), MainCopy.notNow,
            OnboardingCopy.checkingOnlineTitle, OnboardingCopy.checkingOnlineMessage,
            SharedCopy.statusLine(stage: .starting, state: Fixtures.catchingUpState),
        ]
        for sample in samples {
            XCTAssertFalse(sample.contains("!"), sample)
            XCTAssertFalse(sample.contains("\u{2014}"), sample)
            for word in banned {
                let pattern = "\\b\(NSRegularExpression.escapedPattern(for: word))\\b"
                XCTAssertNil(sample.range(of: pattern, options: [.regularExpression, .caseInsensitive]),
                             "\"\(sample)\" contains \"\(word)\"")
            }
        }
        XCTAssertTrue(MainCopy.allStrings.contains(MainCopy.selectionNoticeTitle(count: 12)))
        XCTAssertTrue(OnboardingCopy.allStrings.contains(OnboardingCopy.checkingOnlineMessage))
    }
}

@MainActor
final class CatchUpStoreTests: XCTestCase {
    private let connection = CoreConnection(port: 5555, appToken: "t")

    private func makeStore(_ api: MockLocalAPI) -> AppStore {
        AppStore(dependencies: .init(makeAPI: { _ in api }, openURL: { _ in }, restartCore: {}))
    }

    /// A store in normal use with the notice pending, notebooks loaded.
    private func readyStore() async -> (AppStore, MockLocalAPI) {
        let api = MockLocalAPI(state: Fixtures.selectionNoticeState, notebooks: Fixtures.catchUpLibraryNotebooks)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await store.reloadNotebooks()
        return (store, api)
    }

    private var answeredState: AppState {
        var state = Fixtures.selectionNoticeState
        state.catchUp.unselectedOnServer = 0
        return state
    }

    private func dismissCalls(_ api: MockLocalAPI) -> Int { api.calls.filter { $0 == .dismissCatchUp }.count }

    func testNoticeOnlyInNormalUse() async {
        let (store, _) = await readyStore()
        XCTAssertEqual(store.stage, .ready)
        XCTAssertEqual(store.selectionNoticeCount, 4)

        let first = AppStore.preview(state: Fixtures.firstSyncPendingState)
        XCTAssertEqual(first.selectionNoticeCount, 0)
        let catchingUp = AppStore.preview(state: Fixtures.catchingUpState)
        XCTAssertEqual(catchingUp.stage, .starting)
        XCTAssertEqual(catchingUp.selectionNoticeCount, 0)
        XCTAssertEqual(AppStore.preview(state: Fixtures.readyState).selectionNoticeCount, 0)
    }

    func testTickThemTicksExactlyTheUntickedNotebooksOnlineAndDismissesOnce() async {
        let (store, api) = await readyStore()
        let saved = NotebookList.savedSelection(store.notebooks)
        let ticks = store.notebooksToTickFromNotice(draft: saved)
        XCTAssertEqual(Set(ticks), ["nb-roadmap", "nb-standup", "nb-quarterly", "nb-recipes"])
        XCTAssertTrue(Set(ticks).isDisjoint(with: saved))
        XCTAssertTrue(ticks.allSatisfy { id in store.notebooks.first { $0.uuid == id }?.onServer == true })

        let task = store.dismissSelectionNotice()
        XCTAssertEqual(store.selectionNoticeCount, 0, "gone at once, before the core answers")
        await task.value
        XCTAssertEqual(dismissCalls(api), 1)
        // Ticking alone uploads nothing: no selection saved, no sync started.
        XCTAssertFalse(api.calls.contains { if case .startSync = $0 { return true }; if case .setSelection = $0 { return true }; return false })

        // A poll still showing the old count (sent before the dismissal arrived) does not bring it back.
        await store.refresh()
        XCTAssertEqual(store.selectionNoticeCount, 0)
        api.stateResult = .success(answeredState)
        await store.refresh()
        XCTAssertEqual(store.selectionNoticeCount, 0)
        XCTAssertEqual(dismissCalls(api), 1)
    }

    func testNotNowDismissesWithoutTicking() async {
        let (store, api) = await readyStore()
        await store.dismissSelectionNotice().value
        XCTAssertEqual(store.selectionNoticeCount, 0)
        XCTAssertEqual(dismissCalls(api), 1)
        XCTAssertNil(store.problem, "a dismissal is never reported as a problem")
        api.stateResult = .success(answeredState)
        await store.refresh()
        XCTAssertEqual(store.selectionNoticeCount, 0)
    }

    func testFailedDismissalMayComeBackOnTheNextPollWithoutAProblem() async {
        let (store, api) = await readyStore()
        api.dismissCatchUpResult = .failure(.coreUnreachable)
        await store.dismissSelectionNotice().value
        XCTAssertEqual(store.selectionNoticeCount, 0, "still hidden until the next poll")
        XCTAssertNil(store.problem)
        await store.refresh()
        XCTAssertEqual(store.selectionNoticeCount, 4)
    }

    func testALaterCatchUpCanRaiseTheNoticeAgain() async {
        // Answered, then the user switches account: the core raises a new notice.
        let (store, api) = await readyStore()
        await store.dismissSelectionNotice().value
        api.stateResult = .success(answeredState)
        await store.refresh()
        var again = Fixtures.selectionNoticeState
        again.catchUp.unselectedOnServer = 2
        api.stateResult = .success(again)
        await store.refresh()
        XCTAssertEqual(store.selectionNoticeCount, 2)
    }

    func testCatchUpShowsStartingThenTheFirstSyncOrMainWindow() async {
        let api = MockLocalAPI(state: Fixtures.catchingUpState, notebooks: Fixtures.catchUpLibraryNotebooks)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        XCTAssertEqual(store.stage, .starting)
        XCTAssertFalse(api.calls.contains { if case .firstRunSuggestion = $0 { return true }; return false },
                       "nothing about a first sync is asked while the core is catching up")
        api.stateResult = .success(Fixtures.selectionNoticeState)
        await store.refresh()
        XCTAssertEqual(store.stage, .ready)
        XCTAssertEqual(store.selectionNoticeCount, 4)
    }
}
