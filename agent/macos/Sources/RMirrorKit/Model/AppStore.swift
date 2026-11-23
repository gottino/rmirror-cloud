import Combine
import Foundation

/// Something went wrong with an action the user took. The app turns these into words (`Copy`).
public enum ActionProblem: Equatable, Sendable {
    case coreUnreachable
    case notSignedIn
    case syncAlreadyRunning
    case cloudUnavailable
    case other
    public init(_ error: Error) {
        guard let apiError = error as? LocalAPIError else { self = .other; return }
        switch apiError {
        case .coreUnreachable: self = .coreUnreachable
        case .api(let code, _, _):
            switch code {
            case .notSignedIn: self = .notSignedIn
            case .syncAlreadyRunning: self = .syncAlreadyRunning
            case .cloudTimeout, .cloudError: self = .cloudUnavailable
            case .coreNotReady: self = .coreUnreachable
            default: self = .other
            }
        case .decoding: self = .other
        }
    }
}

/// The outcome of the fallback update check.
public enum UpdateCheckResult: Equatable, Sendable {
    case checked(UpdateCheck)
    /// rMirror's own core is not running (or not reachable), so the internet is not to blame.
    case coreNotRunning
    /// The core answered with an error (usually the cloud could not be reached).
    case failed
}

/// The app's single source of truth. Owns polling of the core and every action a view can take.
/// Views read the published properties and call the methods; they never talk to the API directly.
@MainActor
public final class AppStore: ObservableObject {
    // MARK: Published state

    @Published public private(set) var coreStatus: CoreStatus = .stopped
    @Published public private(set) var state: AppState?
    @Published public private(set) var stage: Stage = .starting
    @Published public private(set) var notebooks: [NotebookEntry] = []
    /// The reMarkable's folders, from the same request as `notebooks`. Empty from a core that does not send them.
    @Published public private(set) var folders: [FolderEntry] = []
    @Published public private(set) var notebooksLoaded = false
    @Published public private(set) var suggestion: FirstRunSuggestion?
    @Published public private(set) var settings: AppSettings?
    @Published public private(set) var deletedNotebooks: [DeletedNotebook] = []
    /// True between "Sign in" and the core reporting a signed-in account.
    @Published public private(set) var isWaitingForSignIn = false
    /// True while a start-sync request is in flight.
    @Published public private(set) var isStartingSync = false
    /// The most recent failed action in the main window, until `dismissProblem()` or the next successful action there.
    @Published public private(set) var problem: ActionProblem?
    /// The same for the settings window, kept apart so each window shows only its own problems.
    @Published public private(set) var settingsProblem: ActionProblem?
    /// The first-run suggestion could not be fetched the last time it was asked for. With no
    /// suggestion yet, the first-sync screen says so calmly instead of spinning forever.
    @Published public private(set) var suggestionUnreachable = false

    // MARK: Dependencies

    public struct Dependencies {
        /// Builds the API client for a running core.
        public var makeAPI: @MainActor (CoreConnection) -> LocalAPI
        public var openURL: @MainActor (URL) -> Void
        public var restartCore: @MainActor () -> Void
        /// The clock, replaceable in tests.
        public var now: @MainActor () -> Date
        public init(
            makeAPI: @escaping @MainActor (CoreConnection) -> LocalAPI,
            openURL: @escaping @MainActor (URL) -> Void,
            restartCore: @escaping @MainActor () -> Void,
            now: @escaping @MainActor () -> Date = { Date() }
        ) {
            self.makeAPI = makeAPI
            self.openURL = openURL
            self.restartCore = restartCore
            self.now = now
        }
    }

    private let dependencies: Dependencies
    private var api: LocalAPI?
    private var connection: CoreConnection?
    private var pollTask: Task<Void, Never>?
    private var guidedSyncActive = false
    private var windowVisible = false
    /// Every state request is numbered. An answer older than one already applied is dropped, and so
    /// is any answer to a request sent before the last action changed the core (`discardBefore`).
    private var lastRequestedRefresh = 0
    private var lastAppliedRefresh = 0
    private var discardRefreshesBefore = 0
    private var lastSuggestionFetch: Date?

    public static let fastPollInterval: TimeInterval = 2
    public static let slowPollInterval: TimeInterval = 15
    /// While the suggestion is not usable yet, ask for it again at most this often.
    public static let suggestionRetryInterval: TimeInterval = 10

    public init(dependencies: Dependencies) {
        self.dependencies = dependencies
    }

    /// A store with fixed content and no core, for screenshots and tests.
    public static func preview(
        state: AppState?,
        core: CoreStatus = .running(CoreConnection(port: 5555, appToken: "preview")),
        api: LocalAPI = MockLocalAPI(),
        notebooks: [NotebookEntry] = [],
        folders: [FolderEntry] = [],
        suggestion: FirstRunSuggestion? = nil,
        settings: AppSettings? = nil,
        guidedSyncActive: Bool = false,
        problem: ActionProblem? = nil,
        isWaitingForSignIn: Bool = false,
        suggestionUnreachable: Bool = false,
        deletedNotebooks: [DeletedNotebook] = []
    ) -> AppStore {
        let store = AppStore(dependencies: Dependencies(makeAPI: { _ in api }, openURL: { _ in }, restartCore: {}))
        store.coreStatus = core
        store.api = api
        store.state = state
        store.notebooks = notebooks
        store.folders = folders
        store.notebooksLoaded = true
        store.suggestion = suggestion
        store.settings = settings
        store.guidedSyncActive = guidedSyncActive
        store.problem = problem
        store.isWaitingForSignIn = isWaitingForSignIn
        store.suggestionUnreachable = suggestionUnreachable
        store.deletedNotebooks = deletedNotebooks
        store.recomputeStage()
        return store
    }

    // MARK: Core lifecycle

    /// Call whenever the supervisor reports a new status.
    public func coreStatusChanged(_ status: CoreStatus) {
        coreStatus = status
        if case .running(let newConnection) = status {
            if newConnection != connection {
                connection = newConnection
                api = dependencies.makeAPI(newConnection)
            }
            startPolling()
        } else {
            connection = nil
            api = nil
            pollTask?.cancel()
            pollTask = nil
            state = nil
            // The guided first sync belongs to the core that ran it; never let its screens come back later.
            guidedSyncActive = false
        }
        recomputeStage()
    }

    /// Polls quickly while a window is open, slowly otherwise.
    public func setWindowVisible(_ visible: Bool) {
        guard visible != windowVisible else { return }
        windowVisible = visible
        // A sign-in abandoned with every window closed must not keep the fast polling going.
        if !visible { isWaitingForSignIn = false }
        if api != nil { startPolling() }
        // The list may have gone stale while no window was open.
        if visible, stage == .ready { Task { await self.reloadNotebooks() } }
    }

    public func restartCore() { dependencies.restartCore() }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refresh()
                let interval = self.pollInterval
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
        }
    }

    private var pollInterval: TimeInterval {
        let syncing = state?.sync.state == .running
        return (windowVisible || syncing || isWaitingForSignIn) ? Self.fastPollInterval : Self.slowPollInterval
    }

    /// Fetches the core's state once and whatever the current screen needs alongside it.
    public func refresh() async {
        guard let api else { return }
        lastRequestedRefresh += 1
        let number = lastRequestedRefresh
        do {
            let newState = try await api.state()
            // Answers can arrive out of order (a slow poll sent before an action): never go back.
            guard number > lastAppliedRefresh, number >= discardRefreshesBefore else { return }
            lastAppliedRefresh = number
            let previousStage = stage
            let previousState = state
            state = newState
            if newState.auth.signedIn { isWaitingForSignIn = false }
            // No sync running or finished in this core: a guided first sync is over.
            if newState.sync.state == .idle { guidedSyncActive = false }
            recomputeStage()
            if stage != previousStage {
                await loadForStage()
            } else if stage == .ready, Self.libraryMayHaveChanged(from: previousState, to: newState) {
                // Pages uploaded in the background (a page added on the tablet): page counts and
                // "synced" figures in the list are now out of date.
                await reloadNotebooks()
            } else if stage == .firstSync, suggestion?.reason != .ok, suggestionDue {
                // Still waiting for notebooks or for the allowance to be known: look again now and then.
                await loadSuggestion()
                if suggestion?.reason == .ok { await reloadNotebooks() }
            }
        } catch {
            // A missed poll is not worth showing; the supervisor reports a dead core.
        }
    }

    /// True when background syncing did something since the last poll: a newer upload time, or the
    /// upload queue just emptied.
    static func libraryMayHaveChanged(from old: AppState?, to new: AppState) -> Bool {
        guard let old else { return false }
        if old.lastUploadAt != new.lastUploadAt { return true }
        return old.queue.pending > 0 && new.queue.pending == 0
    }

    private var suggestionDue: Bool {
        guard let last = lastSuggestionFetch else { return true }
        return dependencies.now().timeIntervalSince(last) >= Self.suggestionRetryInterval
    }

    /// Call after an action changed the core: answers to state requests already in flight are stale.
    private func discardRefreshesInFlight() {
        discardRefreshesBefore = lastRequestedRefresh + 1
    }

    private func recomputeStage() {
        let newStage = Stage.derive(core: coreStatus, state: state, guidedSyncActive: guidedSyncActive)
        if newStage != stage { stage = newStage }
    }

    private func loadForStage() async {
        switch stage {
        case .firstSync:
            await loadSuggestion()
            await reloadNotebooks()
        case .ready:
            await reloadNotebooks()
            await loadSettings()
            await loadDeletedNotebooks()
        default:
            break
        }
    }

    // MARK: Actions

    public func dismissProblem() { problem = nil }

    /// Opens the browser for sign-in. The core hands out a one-time link, finishes the exchange
    /// itself, and polling notices the result.
    public func beginSignIn() async {
        guard let api else { problem = .coreUnreachable; return }
        do {
            let url = try await api.beginSignIn()
            problem = nil
            isWaitingForSignIn = true
            dependencies.openURL(url)
            startPolling()
        } catch {
            problem = ActionProblem(error)
        }
    }

    public func cancelSignIn() { isWaitingForSignIn = false }

    public func signOut() async {
        await perform(from: .settings) { try await $0.signOut() }
        guidedSyncActive = false
        discardRefreshesInFlight()
        await refresh()
    }

    /// Keeps the last good suggestion when a fetch fails; never resets it to nil on an error.
    public func loadSuggestion() async {
        guard let api else { return }
        lastSuggestionFetch = dependencies.now()
        do {
            suggestion = try await api.firstRunSuggestion(max: 3)
            suggestionUnreachable = false
        } catch {
            suggestionUnreachable = true
        }
    }

    public func reloadNotebooks() async {
        guard let api else { return }
        if let response = try? await api.notebooks() {
            if response.folders != folders { folders = response.folders }
            notebooks = response.notebooks
            notebooksLoaded = true
        }
    }

    public func loadSettings() async {
        guard let api else { return }
        if let loaded = try? await api.settings() { settings = loaded }
    }

    public func loadDeletedNotebooks() async {
        guard let api else { return }
        if let loaded = try? await api.deletedNotebooks() { deletedNotebooks = loaded }
    }

    /// The guided first sync: saves the choice and starts syncing in one step.
    /// Does nothing while another start is in flight.
    public func startGuidedSync(notebookUUIDs: [String]) async {
        guard !notebookUUIDs.isEmpty, !isStartingSync else { return }
        isStartingSync = true
        defer { isStartingSync = false }
        let started = await perform { try await $0.startSync(notebookUUIDs: notebookUUIDs, pageLimit: nil) }
        if started {
            guidedSyncActive = true
            discardRefreshesInFlight()
            await refresh()
        }
    }

    /// Leaves the first-sync result screen for the main window.
    public func finishGuidedSync() {
        guidedSyncActive = false
        problem = nil
        recomputeStage()
        Task { await self.loadForStage() }
    }

    /// Main window: saves the selection and syncs it. Selecting and syncing is one action.
    /// Does nothing while another start is in flight.
    /// - Returns: true if the core accepted the sync.
    @discardableResult
    public func syncSelection(notebookUUIDs: [String]) async -> Bool {
        guard !isStartingSync else { return false }
        isStartingSync = true
        defer { isStartingSync = false }
        let started = await perform { try await $0.startSync(notebookUUIDs: notebookUUIDs, pageLimit: nil) }
        if started {
            discardRefreshesInFlight()
            await refresh()
            await reloadNotebooks()
        }
        return started
    }

    /// Saves the selection without starting a sync (new pages in selected notebooks sync on their own).
    /// - Returns: true if the core saved it.
    @discardableResult
    public func saveSelection(notebookUUIDs: [String]) async -> Bool {
        let saved = await perform { try await $0.setSelection(syncAll: false, selectedNotebooks: notebookUUIDs) }
        if saved { await reloadNotebooks() }
        return saved
    }

    public func resumeSync() async {
        if await perform(action: { try await $0.resumeSync() }) { discardRefreshesInFlight() }
        await refresh()
    }

    /// Settings window. Problems go to `settingsProblem`.
    /// - Returns: true if the change means the user has to sign in again.
    @discardableResult
    public func updateSettings(_ update: SettingsUpdate) async -> Bool {
        guard let api else { settingsProblem = .coreUnreachable; return false }
        do {
            let result = try await api.updateSettings(update)
            settingsProblem = nil
            discardRefreshesInFlight()
            await loadSettings()
            await refresh()
            return result.needsSignIn
        } catch {
            settingsProblem = ActionProblem(error)
            return false
        }
    }

    public func dismissSettingsProblem() { settingsProblem = nil }

    public func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async {
        await perform { try await $0.resolveDeletedNotebook(uuid: uuid, action: action) }
        await loadDeletedNotebooks()
    }

    /// The fallback update check (when automatic updates are not set up in this build).
    public func checkForUpdate() async -> UpdateCheckResult {
        guard let api else { return .coreNotRunning }
        do {
            return .checked(try await api.updateCheck())
        } catch {
            return ActionProblem(error) == .coreUnreachable ? .coreNotRunning : .failed
        }
    }

    /// Which window an action came from, so its problem shows only there.
    private enum ProblemOrigin { case main, settings }

    @discardableResult
    private func perform(from origin: ProblemOrigin = .main, action: (LocalAPI) async throws -> Void) async -> Bool {
        guard let api else { report(.coreUnreachable, from: origin); return false }
        do {
            try await action(api)
            report(nil, from: origin)
            return true
        } catch {
            report(ActionProblem(error), from: origin)
            return false
        }
    }

    private func report(_ newProblem: ActionProblem?, from origin: ProblemOrigin) {
        switch origin {
        case .main: problem = newProblem
        case .settings: settingsProblem = newProblem
        }
    }
}
