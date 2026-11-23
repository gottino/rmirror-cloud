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

/// The app's single source of truth. Owns polling of the core and every action a view can take.
/// Views read the published properties and call the methods; they never talk to the API directly.
@MainActor
public final class AppStore: ObservableObject {
    // MARK: Published state

    @Published public private(set) var coreStatus: CoreStatus = .stopped
    @Published public private(set) var state: AppState?
    @Published public private(set) var stage: Stage = .starting
    @Published public private(set) var notebooks: [NotebookEntry] = []
    @Published public private(set) var notebooksLoaded = false
    @Published public private(set) var suggestion: FirstRunSuggestion?
    @Published public private(set) var settings: AppSettings?
    @Published public private(set) var deletedNotebooks: [DeletedNotebook] = []
    /// True between "Sign in" and the core reporting a signed-in account.
    @Published public private(set) var isWaitingForSignIn = false
    /// True while a start-sync request is in flight.
    @Published public private(set) var isStartingSync = false
    /// The most recent failed action, until `dismissProblem()` or the next successful action.
    @Published public private(set) var problem: ActionProblem?

    // MARK: Dependencies

    public struct Dependencies {
        /// Builds the API client for a running core.
        public var makeAPI: @MainActor (CoreConnection) -> LocalAPI
        public var openURL: @MainActor (URL) -> Void
        public var restartCore: @MainActor () -> Void
        public init(
            makeAPI: @escaping @MainActor (CoreConnection) -> LocalAPI,
            openURL: @escaping @MainActor (URL) -> Void,
            restartCore: @escaping @MainActor () -> Void
        ) {
            self.makeAPI = makeAPI
            self.openURL = openURL
            self.restartCore = restartCore
        }
    }

    private let dependencies: Dependencies
    private var api: LocalAPI?
    private var connection: CoreConnection?
    private var pollTask: Task<Void, Never>?
    private var guidedSyncActive = false
    private var windowVisible = false

    public static let fastPollInterval: TimeInterval = 2
    public static let slowPollInterval: TimeInterval = 15

    public init(dependencies: Dependencies) {
        self.dependencies = dependencies
    }

    /// A store with fixed content and no core, for screenshots and tests.
    public static func preview(
        state: AppState?,
        core: CoreStatus = .running(CoreConnection(port: 5555, appToken: "preview")),
        api: LocalAPI = MockLocalAPI(),
        notebooks: [NotebookEntry] = [],
        suggestion: FirstRunSuggestion? = nil,
        settings: AppSettings? = nil,
        guidedSyncActive: Bool = false,
        problem: ActionProblem? = nil,
        isWaitingForSignIn: Bool = false
    ) -> AppStore {
        let store = AppStore(dependencies: Dependencies(makeAPI: { _ in api }, openURL: { _ in }, restartCore: {}))
        store.coreStatus = core
        store.api = api
        store.state = state
        store.notebooks = notebooks
        store.notebooksLoaded = true
        store.suggestion = suggestion
        store.settings = settings
        store.guidedSyncActive = guidedSyncActive
        store.problem = problem
        store.isWaitingForSignIn = isWaitingForSignIn
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
        }
        recomputeStage()
    }

    /// Polls quickly while a window is open, slowly otherwise.
    public func setWindowVisible(_ visible: Bool) {
        guard visible != windowVisible else { return }
        windowVisible = visible
        if api != nil { startPolling() }
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
        do {
            let newState = try await api.state()
            let previousStage = stage
            state = newState
            if newState.auth.signedIn { isWaitingForSignIn = false }
            recomputeStage()
            if stage != previousStage {
                await loadForStage()
            } else if stage == .firstSync, suggestion?.reason != .ok {
                // Still waiting for notebooks or for the allowance to be known: look again.
                await loadSuggestion()
                if suggestion?.reason == .ok { await reloadNotebooks() }
            }
        } catch {
            // A missed poll is not worth showing; the supervisor reports a dead core.
        }
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
        await perform { try await $0.signOut() }
        guidedSyncActive = false
        await refresh()
    }

    public func loadSuggestion() async {
        guard let api else { return }
        suggestion = try? await api.firstRunSuggestion(max: 3)
    }

    public func reloadNotebooks() async {
        guard let api else { return }
        if let response = try? await api.notebooks() {
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
    public func startGuidedSync(notebookUUIDs: [String]) async {
        guard !notebookUUIDs.isEmpty else { return }
        isStartingSync = true
        defer { isStartingSync = false }
        let started = await perform { try await $0.startSync(notebookUUIDs: notebookUUIDs, pageLimit: nil) }
        if started {
            guidedSyncActive = true
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
    public func syncSelection(notebookUUIDs: [String]) async {
        isStartingSync = true
        defer { isStartingSync = false }
        let started = await perform { try await $0.startSync(notebookUUIDs: notebookUUIDs, pageLimit: nil) }
        if started {
            await refresh()
            await reloadNotebooks()
        }
    }

    /// Saves the selection without starting a sync (new pages in selected notebooks sync on their own).
    public func saveSelection(notebookUUIDs: [String]) async {
        let saved = await perform { try await $0.setSelection(syncAll: false, selectedNotebooks: notebookUUIDs) }
        if saved { await reloadNotebooks() }
    }

    public func resumeSync() async {
        await perform { try await $0.resumeSync() }
        await refresh()
    }

    /// - Returns: true if the change means the user has to sign in again.
    @discardableResult
    public func updateSettings(_ update: SettingsUpdate) async -> Bool {
        guard let api else { problem = .coreUnreachable; return false }
        do {
            let result = try await api.updateSettings(update)
            problem = nil
            await loadSettings()
            await refresh()
            return result.needsSignIn
        } catch {
            problem = ActionProblem(error)
            return false
        }
    }

    public func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async {
        await perform { try await $0.resolveDeletedNotebook(uuid: uuid, action: action) }
        await loadDeletedNotebooks()
    }

    public func checkForUpdate() async -> UpdateCheck? {
        guard let api else { return nil }
        return try? await api.updateCheck()
    }

    @discardableResult
    private func perform(_ action: (LocalAPI) async throws -> Void) async -> Bool {
        guard let api else { problem = .coreUnreachable; return false }
        do {
            try await action(api)
            problem = nil
            return true
        } catch {
            problem = ActionProblem(error)
            return false
        }
    }
}
