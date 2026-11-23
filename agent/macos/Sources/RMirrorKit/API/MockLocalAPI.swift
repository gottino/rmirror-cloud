import Foundation

/// In-memory `LocalAPI` for previews, the screenshot renderer and tests. Set the response per endpoint
/// (`Result` so errors can be simulated); calls are recorded in `calls`.
public final class MockLocalAPI: LocalAPI, @unchecked Sendable {
    public enum Call: Equatable, Sendable {
        case state, notebooks, firstRunSuggestion(max: Int), syncProgress, resumeSync, settings, signOut
        case updateCheck, deletedNotebooks, health, beginSignIn
        case setSelection(syncAll: Bool, selectedNotebooks: [String])
        case startSync(notebookUUIDs: [String]?, pageLimit: Int?)
        case updateSettings(SettingsUpdate)
        case resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction)
    }

    private let lock = NSLock()
    private var _stateResult: Result<AppState, LocalAPIError>
    private var _notebooksResult: Result<NotebooksResponse, LocalAPIError>
    private var _suggestionResult: Result<FirstRunSuggestion, LocalAPIError>
    private var _progressResult: Result<SyncProgress, LocalAPIError>
    private var _settingsResult: Result<AppSettings, LocalAPIError>
    private var _updateSettingsResult: Result<SettingsUpdateResult, LocalAPIError> = .success(SettingsUpdateResult())
    private var _deletedResult: Result<[DeletedNotebook], LocalAPIError> = .success([])
    private var _updateCheckResult: Result<UpdateCheck, LocalAPIError>
    private var _healthResult: Result<Bool, LocalAPIError> = .success(true)
    /// Result for the endpoints that return nothing: setSelection, startSync, resumeSync, signOut, resolveDeletedNotebook.
    private var _actionResult: Result<Void, LocalAPIError> = .success(())
    private var _calls: [Call] = []

    public init(state: AppState = Fixtures.readyState,
                notebooks: NotebooksResponse = Fixtures.readyNotebooks,
                suggestion: FirstRunSuggestion = Fixtures.threeNotebookSuggestion,
                settings: AppSettings = Fixtures.settings) {
        _stateResult = .success(state)
        _notebooksResult = .success(notebooks)
        _suggestionResult = .success(suggestion)
        _progressResult = .success(state.sync)
        _settingsResult = .success(settings)
        _updateCheckResult = .success(UpdateCheck(hasUpdate: false, currentVersion: state.coreVersion,
                                                  latestVersion: state.coreVersion, downloadURL: nil))
    }

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock(); defer { lock.unlock() }
        return body()
    }

    public var stateResult: Result<AppState, LocalAPIError> {
        get { locked { _stateResult } }
        set { locked { _stateResult = newValue } }
    }
    public var notebooksResult: Result<NotebooksResponse, LocalAPIError> {
        get { locked { _notebooksResult } }
        set { locked { _notebooksResult = newValue } }
    }
    public var suggestionResult: Result<FirstRunSuggestion, LocalAPIError> {
        get { locked { _suggestionResult } }
        set { locked { _suggestionResult = newValue } }
    }
    public var progressResult: Result<SyncProgress, LocalAPIError> {
        get { locked { _progressResult } }
        set { locked { _progressResult = newValue } }
    }
    public var settingsResult: Result<AppSettings, LocalAPIError> {
        get { locked { _settingsResult } }
        set { locked { _settingsResult = newValue } }
    }
    public var updateSettingsResult: Result<SettingsUpdateResult, LocalAPIError> {
        get { locked { _updateSettingsResult } }
        set { locked { _updateSettingsResult = newValue } }
    }
    public var deletedNotebooksResult: Result<[DeletedNotebook], LocalAPIError> {
        get { locked { _deletedResult } }
        set { locked { _deletedResult = newValue } }
    }
    public var updateCheckResult: Result<UpdateCheck, LocalAPIError> {
        get { locked { _updateCheckResult } }
        set { locked { _updateCheckResult = newValue } }
    }
    public var healthResult: Result<Bool, LocalAPIError> {
        get { locked { _healthResult } }
        set { locked { _healthResult = newValue } }
    }
    public var actionResult: Result<Void, LocalAPIError> {
        get { locked { _actionResult } }
        set { locked { _actionResult = newValue } }
    }

    /// Convenience: make every endpoint fail with `error` (e.g. `.coreUnreachable`).
    public func failEverything(with error: LocalAPIError) {
        locked {
            _stateResult = .failure(error); _notebooksResult = .failure(error); _suggestionResult = .failure(error)
            _progressResult = .failure(error); _settingsResult = .failure(error); _updateSettingsResult = .failure(error)
            _deletedResult = .failure(error); _updateCheckResult = .failure(error); _healthResult = .failure(error)
            _actionResult = .failure(error)
        }
    }

    public var calls: [Call] { locked { _calls } }

    private func record(_ call: Call) { locked { _calls.append(call) } }

    public func state() async throws -> AppState { record(.state); return try stateResult.get() }
    public func notebooks() async throws -> NotebooksResponse { record(.notebooks); return try notebooksResult.get() }
    public func setSelection(syncAll: Bool, selectedNotebooks: [String]) async throws {
        record(.setSelection(syncAll: syncAll, selectedNotebooks: selectedNotebooks))
        try actionResult.get()
    }
    public func firstRunSuggestion(max: Int) async throws -> FirstRunSuggestion {
        record(.firstRunSuggestion(max: max)); return try suggestionResult.get()
    }
    public func startSync(notebookUUIDs: [String]?, pageLimit: Int?) async throws {
        record(.startSync(notebookUUIDs: notebookUUIDs, pageLimit: pageLimit))
        try actionResult.get()
    }
    public func syncProgress() async throws -> SyncProgress { record(.syncProgress); return try progressResult.get() }
    public func resumeSync() async throws { record(.resumeSync); try actionResult.get() }
    public func settings() async throws -> AppSettings { record(.settings); return try settingsResult.get() }
    public func updateSettings(_ update: SettingsUpdate) async throws -> SettingsUpdateResult {
        record(.updateSettings(update)); return try updateSettingsResult.get()
    }
    public var beginSignInResult: Result<URL, LocalAPIError> =
        .success(URL(string: "http://127.0.0.1:5555/auth/bridge?ticket=sample")!)
    public func beginSignIn() async throws -> URL { record(.beginSignIn); return try beginSignInResult.get() }
    public func signOut() async throws { record(.signOut); try actionResult.get() }
    public func deletedNotebooks() async throws -> [DeletedNotebook] {
        record(.deletedNotebooks); return try deletedNotebooksResult.get()
    }
    public func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async throws {
        record(.resolveDeletedNotebook(uuid: uuid, action: action)); try actionResult.get()
    }
    public func updateCheck() async throws -> UpdateCheck { record(.updateCheck); return try updateCheckResult.get() }
    public func health() async throws -> Bool { record(.health); return try healthResult.get() }
}

// MARK: - Fixtures

/// Realistic sample values for each onboarding situation. Dates are fixed so snapshots are stable.
public enum Fixtures {
    public static let now = Date(timeIntervalSince1970: 1_795_507_200) // 2026-11-23T08:00:00Z
    public static let remarkableFolder = "/Users/sample/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
    public static let email = "sample@example.com"

    public static let production = EnvironmentInfo(name: .production, apiURL: "https://rmirror.io/api/v1",
                                                   dashboardURL: "https://rmirror.io")
    public static let idleSync = SyncProgress(state: .idle)

    private static func quota(used: Int, limit: Int = 200) -> QuotaInfo {
        QuotaInfo(used: used, limit: limit, remaining: max(limit - used, 0),
                  resetAt: now.addingTimeInterval(8 * 86_400), fetchedAt: now)
    }

    private static func state(auth: AuthInfo, folder: FolderInfo, watcher: WatcherInfo, queue: QueueInfo = QueueInfo(pending: 0, running: true),
                              quota: QuotaInfo?, firstSyncCompleted: Bool, sync: SyncProgress = idleSync,
                              lastUploadAt: Date? = nil) -> AppState {
        AppState(coreVersion: "2.0.0", auth: auth, environment: production, folder: folder, watcher: watcher,
                 queue: queue, quota: quota, firstSync: FirstSyncInfo(completed: firstSyncCompleted), sync: sync,
                 lastUploadAt: lastUploadAt)
    }

    private static let signedIn = AuthInfo(signedIn: true, email: email, signInRequired: false)
    private static let okFolder = FolderInfo(path: remarkableFolder, state: .ok)
    private static let runningWatcher = WatcherInfo(state: .running, observerAlive: true, lastEventAt: nil, lastRescanAt: now)
    private static let idleWatcher = WatcherInfo(state: .idle, observerAlive: false)

    /// Signed out, nothing known yet.
    public static let signedOutState = state(
        auth: AuthInfo(signedIn: false, email: nil, signInRequired: false),
        folder: okFolder, watcher: idleWatcher, queue: QueueInfo(pending: 0, running: false, pausedReason: .signIn),
        quota: nil, firstSyncCompleted: false)

    /// A stored sign-in exists and is still being checked.
    public static let checkingSignInState = state(
        auth: AuthInfo(signedIn: false, email: nil, signInRequired: false, state: .checking),
        folder: okFolder, watcher: idleWatcher, queue: QueueInfo(pending: 0, running: false, pausedReason: nil),
        quota: nil, firstSyncCompleted: true)

    /// Signed in before, but the cloud cannot be reached right now.
    public static let offlineState = state(
        auth: AuthInfo(signedIn: false, email: email, signInRequired: false, state: .offline),
        folder: okFolder, watcher: idleWatcher, queue: QueueInfo(pending: 0, running: false, pausedReason: .offline),
        quota: nil, firstSyncCompleted: true)

    /// The stored sign-in was rejected: user must sign in again.
    public static let signInRequiredState = state(
        auth: AuthInfo(signedIn: false, email: email, signInRequired: true),
        folder: okFolder, watcher: idleWatcher, queue: QueueInfo(pending: 0, running: false, pausedReason: .signIn),
        quota: nil, firstSyncCompleted: true)

    /// Signed in but the reMarkable desktop app folder does not exist.
    public static let folderMissingState = state(
        auth: signedIn, folder: FolderInfo(path: remarkableFolder, state: .missing), watcher: idleWatcher,
        quota: quota(used: 0), firstSyncCompleted: false)

    /// Folder exists but macOS privacy protection blocks reading it.
    public static let folderUnreadableState = state(
        auth: signedIn, folder: FolderInfo(path: remarkableFolder, state: .unreadable), watcher: idleWatcher,
        quota: quota(used: 0), firstSyncCompleted: false)

    /// Signed in, folder fine, first sync not started yet.
    public static let firstSyncPendingState = state(
        auth: signedIn, folder: okFolder, watcher: runningWatcher, quota: quota(used: 4), firstSyncCompleted: false)

    public static let threeNotebookSuggestion = FirstRunSuggestion(
        notebooks: [
            SuggestedNotebook(uuid: "nb-meeting-notes", name: "Meeting Notes", pageCount: 12),
            SuggestedNotebook(uuid: "nb-book-club", name: "Book Club", pageCount: 8),
            SuggestedNotebook(uuid: "nb-travel-journal", name: "Travel Journal", pageCount: 3),
        ],
        totalPages: 23, quota: SuggestionQuota(limit: 200, remaining: 196), reason: .ok)

    public static let emptySuggestion = FirstRunSuggestion(
        notebooks: [], totalPages: 0, quota: SuggestionQuota(limit: 200, remaining: 196), reason: .noNotebooks)

    public static let runningProgress = SyncProgress(
        state: .running, outcome: nil,
        counts: SyncCounts(uploaded: 4, failed: 0, leftOutByPageLimit: 0, willRetry: 0,
                           notebooksDone: 1, notebooksTotal: 3, pagesTotal: 23),
        startedAt: now.addingTimeInterval(-40), finishedAt: nil)

    /// First sync running: 4 of 23 pages uploaded, 1 of 3 notebooks done.
    public static let firstSyncRunningState = state(
        auth: signedIn, folder: okFolder, watcher: runningWatcher,
        queue: QueueInfo(pending: 19, running: true), quota: quota(used: 4), firstSyncCompleted: false,
        sync: runningProgress, lastUploadAt: now.addingTimeInterval(-5))

    /// Sync done with some failed pages.
    public static let partialProgress = SyncProgress(
        state: .done, outcome: .partial,
        counts: SyncCounts(uploaded: 20, failed: 3, leftOutByPageLimit: 0, willRetry: 0,
                           notebooksDone: 3, notebooksTotal: 3, pagesTotal: 23),
        startedAt: now.addingTimeInterval(-300), finishedAt: now.addingTimeInterval(-60))

    public static let syncDonePartialState = state(
        auth: signedIn, folder: okFolder, watcher: runningWatcher, quota: quota(used: 24), firstSyncCompleted: true,
        sync: partialProgress, lastUploadAt: now.addingTimeInterval(-60))

    /// Normal operation after the first sync.
    public static let readyState = state(
        auth: signedIn, folder: okFolder, watcher: runningWatcher, quota: quota(used: 24), firstSyncCompleted: true,
        sync: SyncProgress(state: .done, outcome: .success,
                           counts: SyncCounts(uploaded: 24, failed: 0, leftOutByPageLimit: 0, willRetry: 0,
                                              notebooksDone: 3, notebooksTotal: 3, pagesTotal: 24),
                           startedAt: now.addingTimeInterval(-3_600), finishedAt: now.addingTimeInterval(-3_500)),
        lastUploadAt: now.addingTimeInterval(-900))

    /// Quota used up: queue paused, uploads waiting.
    public static let quotaExhaustedState = state(
        auth: signedIn, folder: okFolder, watcher: runningWatcher,
        queue: QueueInfo(pending: 7, running: true, pausedReason: .quota),
        quota: quota(used: 200), firstSyncCompleted: true, lastUploadAt: now.addingTimeInterval(-7_200))

    /// About twelve notebooks in a few folders, some selected.
    public static let readyNotebooks: NotebooksResponse = {
        func nb(_ id: String, _ name: String, _ path: [String], pages: Int, selected: Bool, synced: Int,
                opened: TimeInterval) -> NotebookEntry {
            NotebookEntry(uuid: id, name: name, folderPath: path, pageCount: pages,
                          lastOpenedAt: now.addingTimeInterval(-opened),
                          lastModifiedAt: now.addingTimeInterval(-opened - 600),
                          selected: selected, syncedPages: synced)
        }
        return NotebooksResponse(folderState: .ok, syncAll: false, notebooks: [
            nb("nb-meeting-notes", "Meeting Notes", ["Work", "2026"], pages: 12, selected: true, synced: 12, opened: 86_400),
            nb("nb-book-club", "Book Club", [], pages: 8, selected: true, synced: 8, opened: 172_800),
            nb("nb-travel-journal", "Travel Journal", [], pages: 3, selected: true, synced: 3, opened: 259_200),
            nb("nb-roadmap", "Product Roadmap", ["Work", "2026"], pages: 21, selected: false, synced: 0, opened: 345_600),
            nb("nb-standup", "Standup", ["Work"], pages: 45, selected: false, synced: 0, opened: 432_000),
            nb("nb-ideas", "Ideas", ["Work"], pages: 6, selected: false, synced: 0, opened: 518_400),
            nb("nb-recipes", "Recipes", ["Home"], pages: 17, selected: false, synced: 0, opened: 604_800),
            nb("nb-garden", "Garden Plan", ["Home"], pages: 4, selected: false, synced: 0, opened: 691_200),
            nb("nb-budget", "Budget", ["Home", "Finance"], pages: 9, selected: false, synced: 0, opened: 777_600),
            nb("nb-reading", "Reading List", [], pages: 2, selected: false, synced: 0, opened: 864_000),
            nb("nb-sketches", "Sketches", [], pages: 31, selected: false, synced: 0, opened: 950_400),
            nb("nb-quick", "Quick Notes", [], pages: 1, selected: false, synced: 0, opened: 1_036_800),
        ])
    }()

    /// A library as the reMarkable keeps it: folders nested four deep, an empty folder at the top and one
    /// inside Work, two folders called "Archive" in different places, notebooks at the top level, some
    /// ticked, some partly synced, one synced earlier and since unticked, one with no dates at all.
    /// Ticked: Meeting Notes, Kick-off Workshop, Acme interviews (so Clients and Acme are fully ticked and
    /// Work is mixed), Budget (Home mixed), Book Club (Reading mixed), Travel Journal (top level).
    public static let libraryNotebooks: NotebooksResponse = {
        let folders = [
            FolderEntry(uuid: "f-work", name: "Work"),
            FolderEntry(uuid: "f-work-2026", name: "2026", parentUUID: "f-work"),
            FolderEntry(uuid: "f-work-2026-clients", name: "Clients", parentUUID: "f-work-2026"),
            FolderEntry(uuid: "f-work-2026-clients-acme", name: "Acme", parentUUID: "f-work-2026-clients"),
            FolderEntry(uuid: "f-work-2025", name: "2025", parentUUID: "f-work"),
            FolderEntry(uuid: "f-work-archive", name: "Archive", parentUUID: "f-work"),
            FolderEntry(uuid: "f-home", name: "Home"),
            FolderEntry(uuid: "f-home-finance", name: "Finance", parentUUID: "f-home"),
            FolderEntry(uuid: "f-home-archive", name: "Archive", parentUUID: "f-home"),
            FolderEntry(uuid: "f-reading", name: "Reading"),
            FolderEntry(uuid: "f-templates", name: "Templates"),
        ]
        let paths: [String: (path: [String], parent: String?)] = [
            "": ([], nil),
            "w": (["Work"], "f-work"),
            "w26": (["Work", "2026"], "f-work-2026"),
            "cl": (["Work", "2026", "Clients"], "f-work-2026-clients"),
            "acme": (["Work", "2026", "Clients", "Acme"], "f-work-2026-clients-acme"),
            "w25": (["Work", "2025"], "f-work-2025"),
            "h": (["Home"], "f-home"),
            "fin": (["Home", "Finance"], "f-home-finance"),
            "harc": (["Home", "Archive"], "f-home-archive"),
            "r": (["Reading"], "f-reading"),
        ]
        let hour: TimeInterval = 3_600, day: TimeInterval = 86_400
        func nb(_ id: String, _ name: String, in place: String, pages: Int, selected: Bool = false, synced: Int = 0,
                modified: TimeInterval?, opened: TimeInterval? = nil) -> NotebookEntry {
            let p = paths[place]!
            return NotebookEntry(uuid: id, name: name, folderPath: p.path, parentUUID: p.parent, pageCount: pages,
                                 lastOpenedAt: opened.map { now.addingTimeInterval(-$0) },
                                 lastModifiedAt: modified.map { now.addingTimeInterval(-$0) },
                                 selected: selected, syncedPages: synced)
        }
        return NotebooksResponse(folderState: .ok, syncAll: false, folders: folders, notebooks: [
            nb("nb-meeting-notes", "Meeting Notes", in: "w26", pages: 12, selected: true, synced: 12,
               modified: 2 * hour, opened: 2 * hour),
            nb("nb-roadmap", "Product Roadmap", in: "w26", pages: 21, modified: 3 * day, opened: 3 * day),
            nb("nb-kickoff", "Kick-off Workshop", in: "cl", pages: 14, selected: true, synced: 9,
               modified: 26 * hour, opened: 26 * hour),
            nb("nb-acme-interviews", "Acme discovery interviews and stakeholder mapping, second round", in: "acme",
               pages: 38, selected: true, synced: 38, modified: 9 * day, opened: 8 * day),
            nb("nb-standup-2025", "Standup 2025", in: "w25", pages: 45, modified: 330 * day, opened: 300 * day),
            nb("nb-quarterly", "Quarterly Review", in: "w25", pages: 18, synced: 18, modified: 60 * day, opened: 45 * day),
            nb("nb-ideas", "Ideas", in: "w", pages: 6, modified: 5 * day),
            nb("nb-standup", "Standup", in: "w", pages: 45, modified: 20 * hour, opened: 20 * hour),
            nb("nb-recipes", "Recipes", in: "h", pages: 17, modified: 12 * day, opened: 2 * day),
            nb("nb-garden", "Garden Plan", in: "h", pages: 4, modified: 40 * day),
            nb("nb-budget", "Budget", in: "fin", pages: 9, selected: true, synced: 5, modified: 4 * hour, opened: 4 * hour),
            nb("nb-taxes", "Taxes 2025", in: "fin", pages: 11, modified: 90 * day),
            nb("nb-letters", "Old Letters", in: "harc", pages: 7, modified: 400 * day),
            nb("nb-book-club", "Book Club", in: "r", pages: 8, selected: true, synced: 8, modified: 6 * day, opened: 6 * day),
            nb("nb-reading", "Reading List", in: "r", pages: 2, modified: 15 * day),
            nb("nb-travel-journal", "Travel Journal", in: "", pages: 3, selected: true, synced: 3,
               modified: 21 * day, opened: 21 * day),
            nb("nb-sketches", "Sketches", in: "", pages: 31, modified: 7 * day),
            nb("nb-cafe", "Café Ideas", in: "", pages: 5, modified: 2 * day),
            nb("nb-quick", "Quick Notes", in: "", pages: 1, modified: nil),
        ])
    }()

    public static let settings = AppSettings(
        pageLimit: nil, sourceDirectory: remarkableFolder,
        environment: EnvironmentSetting(name: .production, apiURL: "https://rmirror.io/api/v1"),
        environmentPresets: ["production": "https://rmirror.io/api/v1", "staging": "https://staging.rmirror.io/api/v1"])

    public static let deletedNotebooks = [
        DeletedNotebook(uuid: "nb-old-project", name: "Old Project", deletedAt: now.addingTimeInterval(-86_400)),
    ]
}
