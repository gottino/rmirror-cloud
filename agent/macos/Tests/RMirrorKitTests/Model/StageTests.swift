import XCTest
@testable import RMirrorKit

final class StageTests: XCTestCase {
    private let running = CoreStatus.running(CoreConnection(port: 5555, appToken: "t"))

    func testCoreNotRunningIsStarting() {
        XCTAssertEqual(Stage.derive(core: .stopped, state: Fixtures.readyState, guidedSyncActive: false), .starting)
        XCTAssertEqual(Stage.derive(core: .starting, state: nil, guidedSyncActive: false), .starting)
        XCTAssertEqual(Stage.derive(core: .restarting(attempt: 2), state: nil, guidedSyncActive: false), .starting)
        XCTAssertEqual(Stage.derive(core: running, state: nil, guidedSyncActive: false), .starting)
    }

    func testCoreFailureWins() {
        XCTAssertEqual(Stage.derive(core: .failed(.portInUse), state: Fixtures.readyState, guidedSyncActive: false), .coreProblem(.portInUse))
    }

    func testSignInComesBeforeFolderProblems() {
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.signedOutState, guidedSyncActive: false), .signIn(reason: .signedOut))
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.signInRequiredState, guidedSyncActive: false), .signIn(reason: .expired))
    }

    func testCheckingAndOfflineDoNotShowSignIn() {
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.checkingSignInState, guidedSyncActive: false), .starting)
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.offlineState, guidedSyncActive: false), .ready)
        XCTAssertEqual(SharedCopy.statusLine(stage: .ready, state: Fixtures.offlineState), "Waiting for an internet connection")
    }

    func testAuthStateDefaultsFromSignedIn() throws {
        let old = try LocalAPICoding.makeDecoder().decode(AuthInfo.self, from: Data(#"{"signed_in": true, "email": null, "sign_in_required": false}"#.utf8))
        XCTAssertEqual(old.state, .signedIn)
        let new = try LocalAPICoding.makeDecoder().decode(AuthInfo.self, from: Data(#"{"signed_in": false, "sign_in_required": false, "state": "offline"}"#.utf8))
        XCTAssertEqual(new.state, .offline)
    }

    func testFolderStates() {
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.folderMissingState, guidedSyncActive: false), .remarkableMissing)
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.folderUnreadableState, guidedSyncActive: false), .permission)
    }

    func testFirstSyncFlow() {
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.firstSyncPendingState, guidedSyncActive: false), .firstSync)
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.firstSyncRunningState, guidedSyncActive: true), .firstSyncProgress)
        // Relaunched in the middle of a first sync: still show progress.
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.firstSyncRunningState, guidedSyncActive: false), .firstSyncProgress)
    }

    func testResultStaysUntilDismissed() {
        let done = Fixtures.syncDonePartialState
        XCTAssertEqual(Stage.derive(core: running, state: done, guidedSyncActive: true), .firstSyncResult)
        XCTAssertEqual(Stage.derive(core: running, state: done, guidedSyncActive: false), done.firstSync.completed ? .ready : .firstSync)
    }

    func testReady() {
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.readyState, guidedSyncActive: false), .ready)
        XCTAssertEqual(Stage.derive(core: running, state: Fixtures.quotaExhaustedState, guidedSyncActive: false), .ready)
    }
}

@MainActor
final class AppStoreTests: XCTestCase {
    private let connection = CoreConnection(port: 5555, appToken: "t")

    private func makeStore(_ api: MockLocalAPI, opened: @escaping (URL) -> Void = { _ in }) -> AppStore {
        AppStore(dependencies: .init(makeAPI: { _ in api }, openURL: opened, restartCore: {}))
    }

    func testRunningCoreLoadsStateAndStage() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        XCTAssertEqual(store.stage, .firstSync)
        XCTAssertEqual(store.suggestion, Fixtures.threeNotebookSuggestion)
    }

    func testSignInOpensTheBridgeAndWaits() async {
        var opened: URL?
        let store = makeStore(MockLocalAPI(state: Fixtures.signedOutState)) { opened = $0 }
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        await store.beginSignIn()
        XCTAssertEqual(opened?.absoluteString, "http://127.0.0.1:5555/auth/bridge?ticket=sample")
        XCTAssertTrue(store.isWaitingForSignIn)
    }

    func testGuidedSyncMovesToProgress() async {
        let api = MockLocalAPI(state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        api.stateResult = .success(Fixtures.firstSyncRunningState)
        await store.startGuidedSync(notebookUUIDs: ["a"])
        XCTAssertEqual(store.stage, .firstSyncProgress)
        XCTAssertNil(store.problem)
    }

    func testBackgroundUploadReloadsTheNotebookList() async {
        // A page added on the tablet uploads by itself; the list must pick up the new page count.
        let api = MockLocalAPI(state: Fixtures.readyState)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        let before = api.calls.filter { $0 == .notebooks }.count

        await store.refresh()
        XCTAssertEqual(api.calls.filter { $0 == .notebooks }.count, before, "nothing changed: no reload")

        var uploaded = Fixtures.readyState
        uploaded.lastUploadAt = (uploaded.lastUploadAt ?? Fixtures.now).addingTimeInterval(60)
        var changed = Fixtures.readyNotebooks
        changed.notebooks[0].pageCount += 1
        api.stateResult = .success(uploaded)
        api.notebooksResult = .success(changed)
        await store.refresh()
        XCTAssertEqual(api.calls.filter { $0 == .notebooks }.count, before + 1)
        XCTAssertEqual(store.notebooks.first?.pageCount, changed.notebooks[0].pageCount)
    }

    func testEmptiedUploadQueueCountsAsAChange() {
        var busy = Fixtures.readyState
        busy.queue.pending = 2
        var idle = Fixtures.readyState
        idle.queue.pending = 0
        XCTAssertTrue(AppStore.libraryMayHaveChanged(from: busy, to: idle))
        XCTAssertFalse(AppStore.libraryMayHaveChanged(from: idle, to: idle))
        XCTAssertFalse(AppStore.libraryMayHaveChanged(from: nil, to: idle))
    }

    func testFailedActionIsReported() async {
        let api = MockLocalAPI(state: Fixtures.readyState)
        let store = makeStore(api)
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        api.actionResult = .failure(.api(code: .syncAlreadyRunning, status: 409, detail: nil))
        await store.syncSelection(notebookUUIDs: ["a"])
        XCTAssertEqual(store.problem, .syncAlreadyRunning)
    }

    func testCoreStoppingClearsState() async {
        let store = makeStore(MockLocalAPI(state: Fixtures.readyState))
        store.coreStatusChanged(.running(connection))
        await store.refresh()
        XCTAssertEqual(store.stage, .ready)
        store.coreStatusChanged(.failed(.crashLoop(lastExitCode: 1)))
        XCTAssertNil(store.state)
        XCTAssertEqual(store.stage, .coreProblem(.crashLoop(lastExitCode: 1)))
    }
}
