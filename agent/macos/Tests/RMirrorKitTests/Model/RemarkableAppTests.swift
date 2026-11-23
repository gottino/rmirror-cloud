import XCTest
@testable import RMirrorKit

@MainActor
final class RemarkableAppTests: XCTestCase {
    private let connection = CoreConnection(port: 5555, appToken: "t")

    private func makeStore(source: RemarkableAppSource?, api: LocalAPI = MockLocalAPI(),
                           preferences: UserDefaults? = nil) -> AppStore {
        AppStore(dependencies: .init(makeAPI: { _ in api }, openURL: { _ in }, restartCore: {},
                                     remarkableApp: source, preferences: preferences))
    }

    private func waitUntil(_ condition: @MainActor () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = Date().addingTimeInterval(3)
        while !condition() {
            if Date() > deadline { XCTFail("timed out", file: file, line: line); return }
            try? await Task.sleep(nanoseconds: 5_000_000)
        }
    }

    private func withDefaults(_ body: (UserDefaults) throws -> Void) throws {
        let suite = "rmirror.tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        try body(defaults)
    }

    // MARK: Warning rule

    func testWarningOnlyWhenReadyAndNotRunning() {
        XCTAssertTrue(RemarkableApp.showsNotRunningWarning(stage: .ready, appRunning: false))
        XCTAssertFalse(RemarkableApp.showsNotRunningWarning(stage: .ready, appRunning: true))
        let otherStages: [Stage] = [
            .starting, .coreProblem(.portInUse), .signIn(reason: .signedOut), .signIn(reason: .expired),
            .remarkableMissing, .permission, .firstSync, .firstSyncProgress, .firstSyncResult,
        ]
        for stage in otherStages {
            XCTAssertFalse(RemarkableApp.showsNotRunningWarning(stage: stage, appRunning: false), "\(stage)")
        }
    }

    func testStoreWarnsOnlyInReadyStage() {
        let ready = AppStore.preview(state: Fixtures.readyState, remarkableAppRunning: false)
        XCTAssertEqual(ready.stage, .ready)
        XCTAssertTrue(ready.showsRemarkableAppWarning)
        XCTAssertFalse(AppStore.preview(state: Fixtures.readyState).showsRemarkableAppWarning)
        for state in [Fixtures.signedOutState, Fixtures.folderMissingState, Fixtures.folderUnreadableState,
                      Fixtures.firstSyncPendingState] {
            let store = AppStore.preview(state: state, remarkableAppRunning: false)
            XCTAssertNotEqual(store.stage, .ready)
            XCTAssertFalse(store.showsRemarkableAppWarning, "\(store.stage)")
        }
    }

    func testNoSourceNeverWarns() {
        let store = makeStore(source: nil)
        XCTAssertTrue(store.remarkableAppRunning)
        store.openRemarkableAppAtStartIfWanted()
        store.openRemarkableApp()
    }

    // MARK: Launch and quit events

    func testFollowsLaunchAndQuitEvents() async {
        let source = FakeRemarkableAppSource(isRunning: false)
        let store = makeStore(source: source, api: MockLocalAPI(state: Fixtures.readyState))
        XCTAssertFalse(store.remarkableAppRunning, "initial value comes from the source")
        store.coreStatusChanged(.running(connection))
        await waitUntil { store.stage == .ready }
        XCTAssertTrue(store.showsRemarkableAppWarning)

        source.simulate(running: true)
        XCTAssertTrue(store.remarkableAppRunning)
        XCTAssertFalse(store.showsRemarkableAppWarning, "the warning clears by itself once the app launches")

        source.simulate(running: false)
        XCTAssertTrue(store.showsRemarkableAppWarning)
        store.coreStatusChanged(.stopped)
    }

    func testOpenButtonOpensInForeground() {
        let source = FakeRemarkableAppSource(isRunning: false)
        let store = makeStore(source: source)
        store.openRemarkableApp()
        XCTAssertEqual(source.openCalls, [false])
        XCTAssertTrue(store.remarkableAppInstalled)
    }

    func testOpenWhenNotInstalledHidesTheButtonAndDoesNothingElse() {
        let source = FakeRemarkableAppSource(isRunning: false, isInstalled: false)
        let store = makeStore(source: source)
        XCTAssertFalse(store.remarkableAppInstalled)
        source.isInstalled = true
        source.simulate(running: false)
        XCTAssertTrue(store.remarkableAppInstalled, "installed later: picked up with the next event")
        source.isInstalled = false
        store.openRemarkableApp()
        XCTAssertFalse(store.remarkableAppInstalled)
        XCTAssertNil(store.problem)
    }

    // MARK: Open at start

    func testOpensAtStartDecision() {
        XCTAssertTrue(RemarkableApp.opensAtStart(preferenceOn: true, appRunning: false, alreadyTried: false))
        XCTAssertFalse(RemarkableApp.opensAtStart(preferenceOn: false, appRunning: false, alreadyTried: false))
        XCTAssertFalse(RemarkableApp.opensAtStart(preferenceOn: true, appRunning: true, alreadyTried: false))
        XCTAssertFalse(RemarkableApp.opensAtStart(preferenceOn: true, appRunning: false, alreadyTried: true))
    }

    func testSettingOnAndNotRunningOpensOnceInBackground() throws {
        try withDefaults { defaults in
            RemarkableAppPreferences(opensAtStart: true).save(to: defaults)
            let source = FakeRemarkableAppSource(isRunning: false)
            let store = makeStore(source: source, preferences: defaults)
            store.openRemarkableAppAtStartIfWanted()
            XCTAssertEqual(source.openCalls, [true], "hidden, without activation")
            // The user quits the reMarkable app later: rMirror does not reopen it.
            source.simulate(running: true)
            source.simulate(running: false)
            store.openRemarkableAppAtStartIfWanted()
            XCTAssertEqual(source.openCalls, [true])
        }
    }

    func testSettingOffOrAlreadyRunningDoesNotOpen() throws {
        try withDefaults { defaults in
            let off = FakeRemarkableAppSource(isRunning: false)
            makeStore(source: off, preferences: defaults).openRemarkableAppAtStartIfWanted()
            XCTAssertEqual(off.openCalls, [])

            RemarkableAppPreferences(opensAtStart: true).save(to: defaults)
            let running = FakeRemarkableAppSource(isRunning: true)
            makeStore(source: running, preferences: defaults).openRemarkableAppAtStartIfWanted()
            XCTAssertEqual(running.openCalls, [])
        }
    }

    // MARK: Preference

    func testPreferenceDefaultsOffAndPersists() throws {
        try withDefaults { defaults in
            XCTAssertEqual(RemarkableAppPreferences.load(from: defaults), RemarkableAppPreferences(opensAtStart: false))
            let store = makeStore(source: FakeRemarkableAppSource(), preferences: defaults)
            XCTAssertFalse(store.opensRemarkableAppAtStart)
            store.setOpensRemarkableAppAtStart(true)
            XCTAssertTrue(RemarkableAppPreferences.load(from: defaults).opensAtStart)
            XCTAssertTrue(makeStore(source: nil, preferences: defaults).opensRemarkableAppAtStart, "read at the next start")
            store.setOpensRemarkableAppAtStart(false)
            XCTAssertFalse(RemarkableAppPreferences.load(from: defaults).opensAtStart)
        }
    }

    // MARK: Copy

    func testCopy() {
        XCTAssertEqual(MainCopy.remarkableNotRunningTitle, "The reMarkable app isn't running")
        XCTAssertTrue(MainCopy.remarkableNotRunningBody.contains("New pages won't arrive"))
        XCTAssertEqual(MainCopy.openRemarkable, "Open reMarkable")
        XCTAssertEqual(AppCopy.StatusMenu.openRemarkable, "Open reMarkable")
        XCTAssertEqual(SettingsCopy.openRemarkableAtStart, "Open the reMarkable app when rMirror starts")
        // The banned-word checks of each Copy file cover these strings through `allStrings`.
        XCTAssertTrue(MainCopy.allStrings.contains(MainCopy.remarkableNotRunningBody))
        XCTAssertTrue(AppCopy.allStrings.contains(AppCopy.StatusMenu.remarkableNotRunning))
        XCTAssertTrue(SettingsCopy.generalStrings.contains(SettingsCopy.openRemarkableAtStartExplanation))
    }
}
