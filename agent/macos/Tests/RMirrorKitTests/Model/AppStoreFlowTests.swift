import XCTest
@testable import RMirrorKit

/// A `LocalAPI` whose `state()` and `startSync` answers the test releases by hand, in any order.
/// Everything else goes straight to a `MockLocalAPI`.
final class GatedLocalAPI: LocalAPI, @unchecked Sendable {
    let base: MockLocalAPI
    private let lock = NSLock()
    private var _gateState = false
    private var _gateStartSync = false
    private var pendingStates: [CheckedContinuation<AppState, Error>] = []
    private var pendingStarts: [CheckedContinuation<Void, Error>] = []

    init(_ base: MockLocalAPI) { self.base = base }

    private func locked<T>(_ body: () -> T) -> T { lock.lock(); defer { lock.unlock() }; return body() }

    var gateState: Bool {
        get { locked { _gateState } }
        set { locked { _gateState = newValue } }
    }
    var gateStartSync: Bool {
        get { locked { _gateStartSync } }
        set { locked { _gateStartSync = newValue } }
    }
    var pendingStateCount: Int { locked { pendingStates.count } }
    var pendingStartCount: Int { locked { pendingStarts.count } }

    /// Answers the `index`-th waiting state request (in the order they were sent) with `state`.
    func releaseState(_ index: Int, with state: AppState) {
        let continuation = locked { pendingStates.remove(at: index) }
        continuation.resume(returning: state)
    }

    func releaseStart() {
        let continuation = locked { pendingStarts.removeFirst() }
        continuation.resume(returning: ())
    }

    func state() async throws -> AppState {
        guard gateState else { return try await base.state() }
        return try await withCheckedThrowingContinuation { continuation in
            locked { pendingStates.append(continuation) }
        }
    }

    func startSync(notebookUUIDs: [String]?, pageLimit: Int?) async throws {
        if gateStartSync {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                locked { pendingStarts.append(continuation) }
            }
        }
        try await base.startSync(notebookUUIDs: notebookUUIDs, pageLimit: pageLimit)
    }

    func notebooks() async throws -> NotebooksResponse { try await base.notebooks() }
    func setSelection(syncAll: Bool, selectedNotebooks: [String]) async throws {
        try await base.setSelection(syncAll: syncAll, selectedNotebooks: selectedNotebooks)
    }
    func firstRunSuggestion(max: Int) async throws -> FirstRunSuggestion { try await base.firstRunSuggestion(max: max) }
    func syncProgress() async throws -> SyncProgress { try await base.syncProgress() }
    func resumeSync() async throws { try await base.resumeSync() }
    func settings() async throws -> AppSettings { try await base.settings() }
    func updateSettings(_ update: SettingsUpdate) async throws -> SettingsUpdateResult { try await base.updateSettings(update) }
    func beginSignIn() async throws -> URL { try await base.beginSignIn() }
    func signOut() async throws { try await base.signOut() }
    func deletedNotebooks() async throws -> [DeletedNotebook] { try await base.deletedNotebooks() }
    func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async throws {
        try await base.resolveDeletedNotebook(uuid: uuid, action: action)
    }
    func updateCheck() async throws -> UpdateCheck { try await base.updateCheck() }
    func health() async throws -> Bool { try await base.health() }
}

@MainActor
final class AppStoreFlowTests: XCTestCase {
    private let connection = CoreConnection(port: 5555, appToken: "t")
    private var clock = Date(timeIntervalSince1970: 1_795_507_200)

    private func makeStore(_ api: LocalAPI) -> AppStore {
        AppStore(dependencies: .init(makeAPI: { _ in api }, openURL: { _ in }, restartCore: {},
                                     now: { [unowned self] in self.clock }))
    }

    private func waitUntil(_ condition: @MainActor () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = Date().addingTimeInterval(3)
        while !condition() {
            if Date() > deadline { XCTFail("timed out", file: file, line: line); return }
            try? await Task.sleep(nanoseconds: 5_000_000)
        }
    }

    /// Lets the store's own first poll (started by `coreStatusChanged`) finish, so it cannot mix
    /// with what a test drives by hand. That poll then sleeps for the slow interval (15 s).
    private func settle() async { try? await Task.sleep(nanoseconds: 50_000_000) }

    /// A state like `firstSyncRunningState` but with the sync finished, as after a later sync from the main window.
    private var laterSyncDoneState: AppState {
        var state = Fixtures.readyState
        state.sync = Fixtures.partialProgress
        return state
    }

    // MARK: S8 guided first sync does not survive

    func testGuidedSyncDoesNotSurviveACoreRestart() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        api.stateResult = .success(Fixtures.firstSyncRunningState)
        await store.startGuidedSync(notebookUUIDs: ["nb-meeting-notes"])
        XCTAssertEqual(store.stage, .firstSyncProgress)

        // The core restarts in the middle; afterwards a sync started from the main window finishes.
        store.coreStatusChanged(.restarting(attempt: 1))
        store.coreStatusChanged(.running(CoreConnection(port: 5555, appToken: "new")))
        api.stateResult = .success(laterSyncDoneState)
        await store.refresh()
        XCTAssertEqual(store.stage, .ready, "the first-sync result must not take over the main window")
    }

    func testIdleSyncEndsTheGuidedSync() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        api.stateResult = .success(Fixtures.firstSyncRunningState)
        await store.startGuidedSync(notebookUUIDs: ["nb-meeting-notes"])
        XCTAssertEqual(store.stage, .firstSyncProgress)

        var idle = Fixtures.readyState
        idle.sync = SyncProgress(state: .idle)
        api.stateResult = .success(idle)
        await store.refresh()
        XCTAssertEqual(store.stage, .ready)
        api.stateResult = .success(laterSyncDoneState)
        await store.refresh()
        XCTAssertEqual(store.stage, .ready)
    }

    // MARK: S11 stale answers

    func testAPollSentBeforeTheSyncStartsCannotDragTheStageBack() async {
        let base = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let api = GatedLocalAPI(base)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await settle()
        XCTAssertEqual(store.stage, .firstSync)

        // A poll goes out and is slow to come back.
        api.gateState = true
        let slowPoll = Task { await store.refresh() }
        await waitUntil { api.pendingStateCount == 1 }

        // Meanwhile the user starts the first sync; the core answers at once.
        api.gateState = false
        base.stateResult = .success(Fixtures.firstSyncRunningState)
        await store.startGuidedSync(notebookUUIDs: ["nb-meeting-notes"])
        XCTAssertEqual(store.stage, .firstSyncProgress)

        // Now the old poll answers with the state from before the start.
        api.releaseState(0, with: Fixtures.firstSyncPendingState)
        await slowPoll.value
        XCTAssertEqual(store.stage, .firstSyncProgress)
        XCTAssertEqual(store.state?.sync.state, .running)
    }

    func testAnswersArrivingOutOfOrderKeepTheNewest() async {
        let base = MockLocalAPI(state: Fixtures.readyState)
        let api = GatedLocalAPI(base)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await settle()

        api.gateState = true
        let first = Task { await store.refresh() }
        await waitUntil { api.pendingStateCount == 1 }
        let second = Task { await store.refresh() }
        await waitUntil { api.pendingStateCount == 2 }

        api.releaseState(1, with: Fixtures.quotaExhaustedState)  // newer answers first
        await second.value
        api.releaseState(0, with: Fixtures.readyState)
        await first.value
        XCTAssertEqual(store.state, Fixtures.quotaExhaustedState)
    }

    func testStartingTwiceSendsOneRequest() async {
        let base = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let api = GatedLocalAPI(base)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await settle()

        api.gateStartSync = true
        let first = Task { await store.startGuidedSync(notebookUUIDs: ["a"]) }
        await waitUntil { api.pendingStartCount == 1 }
        XCTAssertTrue(store.isStartingSync)
        await store.startGuidedSync(notebookUUIDs: ["a"])
        let accepted = await store.syncSelection(notebookUUIDs: ["a"])
        XCTAssertFalse(accepted)
        XCTAssertEqual(api.pendingStartCount, 1)
        api.releaseStart()
        await first.value
        let starts = base.calls.filter { if case .startSync = $0 { return true } else { return false } }
        XCTAssertEqual(starts.count, 1)
        XCTAssertFalse(store.isStartingSync)
    }

    // MARK: S12 suggestion

    private func suggestionFetches(_ api: MockLocalAPI) -> Int {
        api.calls.filter { if case .firstRunSuggestion = $0 { return true } else { return false } }.count
    }

    func testSuggestionKeepsTheLastGoodOneAndIsRetriedEveryTenSeconds() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.emptySuggestion)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await settle()
        XCTAssertEqual(store.suggestion, Fixtures.emptySuggestion)
        let initial = suggestionFetches(api)
        XCTAssertGreaterThanOrEqual(initial, 1)

        api.suggestionResult = .failure(.coreUnreachable)
        clock += 2
        await store.refresh()
        XCTAssertEqual(suggestionFetches(api), initial, "not on every 2 s poll")
        clock += 9
        await store.refresh()
        XCTAssertEqual(suggestionFetches(api), initial + 1)
        XCTAssertEqual(store.suggestion, Fixtures.emptySuggestion, "a failed fetch keeps the last good suggestion")
        XCTAssertTrue(store.suggestionUnreachable)

        api.suggestionResult = .success(Fixtures.threeNotebookSuggestion)
        clock += 10
        await store.refresh()
        XCTAssertEqual(store.suggestion, Fixtures.threeNotebookSuggestion)
        XCTAssertFalse(store.suggestionUnreachable)
        clock += 30
        await store.refresh()
        XCTAssertEqual(suggestionFetches(api), initial + 2, "a usable suggestion is not fetched again")
    }

    func testUnreachableSuggestionIsReportedWhenThereIsNone() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState)
        api.suggestionResult = .failure(.api(code: .cloudTimeout, status: 504, detail: nil))
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        XCTAssertNil(store.suggestion)
        XCTAssertTrue(store.suggestionUnreachable)
    }

    // MARK: S14a, S14b

    func testClosingEveryWindowEndsAnAbandonedSignIn() async {
        let store = makeStore(MockLocalAPI(state: Fixtures.signedOutState))
        store.coreStatusChanged(.running(connection))
        store.setWindowVisible(true)
        await store.refresh()
        await store.beginSignIn()
        XCTAssertTrue(store.isWaitingForSignIn)
        store.setWindowVisible(false)
        XCTAssertFalse(store.isWaitingForSignIn)
    }

    func testSettingsAndMainWindowKeepTheirOwnProblems() async {
        let api = MockLocalAPI(state: Fixtures.readyState)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()

        api.updateSettingsResult = .failure(.api(code: .syncAlreadyRunning, status: 409, detail: nil))
        await store.updateSettings(SettingsUpdate(pageLimit: .some(10)))
        XCTAssertEqual(store.settingsProblem, .syncAlreadyRunning)
        XCTAssertNil(store.problem)

        api.actionResult = .failure(.api(code: .cloudError, status: 502, detail: nil))
        await store.syncSelection(notebookUUIDs: ["a"])
        XCTAssertEqual(store.problem, .cloudUnavailable)
        XCTAssertEqual(store.settingsProblem, .syncAlreadyRunning)

        api.actionResult = .success(())
        await store.signOut()
        XCTAssertNil(store.settingsProblem)
        XCTAssertEqual(store.problem, .cloudUnavailable, "signing out in Settings leaves the main window's problem alone")
    }
}
