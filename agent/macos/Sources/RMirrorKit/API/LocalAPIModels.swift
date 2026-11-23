import Foundation

// MARK: - Date coding

/// ISO 8601 handling for the local API: with or without fractional seconds, with `Z` or an offset,
/// and (leniently) without any zone, which is read as UTC.
public enum LocalAPICoding {
    public static func parseDate(_ string: String) -> Date? {
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = fractional.date(from: string) ?? plain.date(from: string) { return d }
        // Zone-less timestamps: treat as UTC.
        if !string.hasSuffix("Z"), string.range(of: #"[+-]\d{2}:?\d{2}$"#, options: .regularExpression) == nil {
            let withZone = string + "Z"
            return fractional.date(from: withZone) ?? plain.date(from: withZone)
        }
        return nil
    }

    public static func formatDate(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: date)
    }

    public static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            guard let date = parseDate(raw) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                        debugDescription: "Invalid ISO 8601 date: \(raw)"))
            }
            return date
        }
        return decoder
    }

    public static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var c = encoder.singleValueContainer()
            try c.encode(formatDate(date))
        }
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

// MARK: - /api/v2/state

public struct AuthInfo: Codable, Equatable, Sendable {
    public var signedIn: Bool
    public var email: String?
    public var signInRequired: Bool

    public init(signedIn: Bool, email: String? = nil, signInRequired: Bool = false) {
        self.signedIn = signedIn
        self.email = email
        self.signInRequired = signInRequired
    }

    enum CodingKeys: String, CodingKey {
        case signedIn = "signed_in"
        case email
        case signInRequired = "sign_in_required"
    }
}

public struct EnvironmentInfo: Codable, Equatable, Sendable {
    public var name: EnvironmentName
    public var apiURL: String
    public var dashboardURL: String?

    public init(name: EnvironmentName, apiURL: String, dashboardURL: String? = nil) {
        self.name = name
        self.apiURL = apiURL
        self.dashboardURL = dashboardURL
    }

    enum CodingKeys: String, CodingKey {
        case name
        case apiURL = "api_url"
        case dashboardURL = "dashboard_url"
    }
}

public struct FolderInfo: Codable, Equatable, Sendable {
    public var path: String?
    public var state: FolderState

    public init(path: String?, state: FolderState) {
        self.path = path
        self.state = state
    }

    enum CodingKeys: String, CodingKey { case path, state }
}

public struct WatcherInfo: Codable, Equatable, Sendable {
    public var state: WatcherState
    public var observerAlive: Bool
    public var lastEventAt: Date?
    public var lastRescanAt: Date?

    public init(state: WatcherState, observerAlive: Bool, lastEventAt: Date? = nil, lastRescanAt: Date? = nil) {
        self.state = state
        self.observerAlive = observerAlive
        self.lastEventAt = lastEventAt
        self.lastRescanAt = lastRescanAt
    }

    enum CodingKeys: String, CodingKey {
        case state
        case observerAlive = "observer_alive"
        case lastEventAt = "last_event_at"
        case lastRescanAt = "last_rescan_at"
    }
}

public struct QueueInfo: Codable, Equatable, Sendable {
    public var pending: Int
    public var running: Bool
    public var pausedReason: PausedReason?

    public init(pending: Int, running: Bool, pausedReason: PausedReason? = nil) {
        self.pending = pending
        self.running = running
        self.pausedReason = pausedReason
    }

    enum CodingKeys: String, CodingKey {
        case pending, running
        case pausedReason = "paused_reason"
    }
}

/// Quota snapshot. `limit == -1` means unlimited; then `remaining` is nil.
public struct QuotaInfo: Codable, Equatable, Sendable {
    public var used: Int
    public var limit: Int
    public var remaining: Int?
    public var resetAt: Date?
    public var fetchedAt: Date?

    public init(used: Int, limit: Int, remaining: Int?, resetAt: Date? = nil, fetchedAt: Date? = nil) {
        self.used = used
        self.limit = limit
        self.remaining = remaining
        self.resetAt = resetAt
        self.fetchedAt = fetchedAt
    }

    public var isUnlimited: Bool { limit < 0 }
    public var isExhausted: Bool { !isUnlimited && (remaining ?? 0) <= 0 }

    enum CodingKeys: String, CodingKey {
        case used, limit, remaining
        case resetAt = "reset_at"
        case fetchedAt = "fetched_at"
    }
}

public struct FirstSyncInfo: Codable, Equatable, Sendable {
    public var completed: Bool

    public init(completed: Bool) { self.completed = completed }

    enum CodingKeys: String, CodingKey { case completed }
}

public struct SyncCounts: Codable, Equatable, Sendable {
    public var uploaded: Int
    public var failed: Int
    public var leftOutByPageLimit: Int
    public var willRetry: Int
    public var notebooksDone: Int
    public var notebooksTotal: Int
    /// nil when the core does not know yet.
    public var pagesTotal: Int?

    public init(uploaded: Int = 0, failed: Int = 0, leftOutByPageLimit: Int = 0, willRetry: Int = 0,
                notebooksDone: Int = 0, notebooksTotal: Int = 0, pagesTotal: Int? = nil) {
        self.uploaded = uploaded
        self.failed = failed
        self.leftOutByPageLimit = leftOutByPageLimit
        self.willRetry = willRetry
        self.notebooksDone = notebooksDone
        self.notebooksTotal = notebooksTotal
        self.pagesTotal = pagesTotal
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        uploaded = try c.decodeIfPresent(Int.self, forKey: .uploaded) ?? 0
        failed = try c.decodeIfPresent(Int.self, forKey: .failed) ?? 0
        leftOutByPageLimit = try c.decodeIfPresent(Int.self, forKey: .leftOutByPageLimit) ?? 0
        willRetry = try c.decodeIfPresent(Int.self, forKey: .willRetry) ?? 0
        notebooksDone = try c.decodeIfPresent(Int.self, forKey: .notebooksDone) ?? 0
        notebooksTotal = try c.decodeIfPresent(Int.self, forKey: .notebooksTotal) ?? 0
        pagesTotal = try c.decodeIfPresent(Int.self, forKey: .pagesTotal)
    }

    enum CodingKeys: String, CodingKey {
        case uploaded, failed
        case leftOutByPageLimit = "left_out_by_page_limit"
        case willRetry = "will_retry"
        case notebooksDone = "notebooks_done"
        case notebooksTotal = "notebooks_total"
        case pagesTotal = "pages_total"
    }
}

/// `GET /api/v2/sync/progress`, also embedded as `sync` in `/api/v2/state`.
public struct SyncProgress: Codable, Equatable, Sendable {
    public var state: SyncState
    public var outcome: SyncOutcome?
    public var counts: SyncCounts
    public var startedAt: Date?
    public var finishedAt: Date?

    public init(state: SyncState, outcome: SyncOutcome? = nil, counts: SyncCounts = SyncCounts(),
                startedAt: Date? = nil, finishedAt: Date? = nil) {
        self.state = state
        self.outcome = outcome
        self.counts = counts
        self.startedAt = startedAt
        self.finishedAt = finishedAt
    }

    enum CodingKeys: String, CodingKey {
        case state, outcome, counts
        case startedAt = "started_at"
        case finishedAt = "finished_at"
    }
}

/// `GET /api/v2/state`.
public struct AppState: Codable, Equatable, Sendable {
    public var apiVersion: Int
    public var coreVersion: String
    public var auth: AuthInfo
    public var environment: EnvironmentInfo
    public var folder: FolderInfo
    public var watcher: WatcherInfo
    public var queue: QueueInfo
    public var quota: QuotaInfo?
    public var firstSync: FirstSyncInfo
    public var sync: SyncProgress
    public var lastUploadAt: Date?

    public init(apiVersion: Int = 2, coreVersion: String, auth: AuthInfo, environment: EnvironmentInfo,
                folder: FolderInfo, watcher: WatcherInfo, queue: QueueInfo, quota: QuotaInfo?,
                firstSync: FirstSyncInfo, sync: SyncProgress, lastUploadAt: Date? = nil) {
        self.apiVersion = apiVersion
        self.coreVersion = coreVersion
        self.auth = auth
        self.environment = environment
        self.folder = folder
        self.watcher = watcher
        self.queue = queue
        self.quota = quota
        self.firstSync = firstSync
        self.sync = sync
        self.lastUploadAt = lastUploadAt
    }

    enum CodingKeys: String, CodingKey {
        case apiVersion = "api_version"
        case coreVersion = "core_version"
        case auth, environment, folder, watcher, queue, quota
        case firstSync = "first_sync"
        case sync
        case lastUploadAt = "last_upload_at"
    }
}

// MARK: - Notebooks and selection

public struct NotebookEntry: Codable, Equatable, Sendable, Identifiable {
    public var uuid: String
    public var name: String
    /// Chain of parent folder names, outermost first. Empty at the top level.
    public var folderPath: [String]
    public var documentType: String
    public var pageCount: Int
    public var lastOpenedAt: Date?
    public var lastModifiedAt: Date?
    public var selected: Bool
    public var syncedPages: Int

    public var id: String { uuid }

    public init(uuid: String, name: String, folderPath: [String] = [], documentType: String = "notebook",
                pageCount: Int, lastOpenedAt: Date? = nil, lastModifiedAt: Date? = nil,
                selected: Bool = false, syncedPages: Int = 0) {
        self.uuid = uuid
        self.name = name
        self.folderPath = folderPath
        self.documentType = documentType
        self.pageCount = pageCount
        self.lastOpenedAt = lastOpenedAt
        self.lastModifiedAt = lastModifiedAt
        self.selected = selected
        self.syncedPages = syncedPages
    }

    enum CodingKeys: String, CodingKey {
        case uuid, name
        case folderPath = "folder_path"
        case documentType = "document_type"
        case pageCount = "page_count"
        case lastOpenedAt = "last_opened_at"
        case lastModifiedAt = "last_modified_at"
        case selected
        case syncedPages = "synced_pages"
    }
}

public struct NotebooksResponse: Codable, Equatable, Sendable {
    public var folderState: FolderState
    public var syncAll: Bool
    public var notebooks: [NotebookEntry]

    public init(folderState: FolderState, syncAll: Bool, notebooks: [NotebookEntry]) {
        self.folderState = folderState
        self.syncAll = syncAll
        self.notebooks = notebooks
    }

    enum CodingKeys: String, CodingKey {
        case folderState = "folder_state"
        case syncAll = "sync_all"
        case notebooks
    }
}

/// Body of `PUT /api/v2/selection`.
public struct SelectionRequest: Codable, Equatable, Sendable {
    public var syncAll: Bool
    public var selectedNotebooks: [String]

    public init(syncAll: Bool, selectedNotebooks: [String]) {
        self.syncAll = syncAll
        self.selectedNotebooks = selectedNotebooks
    }

    enum CodingKeys: String, CodingKey {
        case syncAll = "sync_all"
        case selectedNotebooks = "selected_notebooks"
    }
}

/// `{"ok": true}` style acknowledgement.
public struct OKResponse: Codable, Equatable, Sendable {
    public var ok: Bool
    public init(ok: Bool = true) { self.ok = ok }
}

// MARK: - First run suggestion

public struct SuggestedNotebook: Codable, Equatable, Sendable, Identifiable {
    public var uuid: String
    public var name: String
    public var pageCount: Int

    public var id: String { uuid }

    public init(uuid: String, name: String, pageCount: Int) {
        self.uuid = uuid
        self.name = name
        self.pageCount = pageCount
    }

    enum CodingKeys: String, CodingKey {
        case uuid, name
        case pageCount = "page_count"
    }
}

public struct SuggestionQuota: Codable, Equatable, Sendable {
    /// -1 means unlimited.
    public var limit: Int
    /// nil when unlimited.
    public var remaining: Int?

    public init(limit: Int, remaining: Int?) {
        self.limit = limit
        self.remaining = remaining
    }

    public var isUnlimited: Bool { limit < 0 }

    enum CodingKeys: String, CodingKey { case limit, remaining }
}

public struct FirstRunSuggestion: Codable, Equatable, Sendable {
    public var notebooks: [SuggestedNotebook]
    public var totalPages: Int
    public var quota: SuggestionQuota?
    public var reason: SuggestionReason

    public init(notebooks: [SuggestedNotebook], totalPages: Int, quota: SuggestionQuota?, reason: SuggestionReason) {
        self.notebooks = notebooks
        self.totalPages = totalPages
        self.quota = quota
        self.reason = reason
    }

    enum CodingKeys: String, CodingKey {
        case notebooks
        case totalPages = "total_pages"
        case quota, reason
    }
}

// MARK: - Sync start

/// Body of `POST /api/v2/sync/start`. `notebook_uuids` is omitted when nil; `page_limit` is always sent
/// (explicit `null` means "no limit").
public struct StartSyncRequest: Codable, Equatable, Sendable {
    public var notebookUUIDs: [String]?
    public var pageLimit: Int?

    public init(notebookUUIDs: [String]? = nil, pageLimit: Int? = nil) {
        self.notebookUUIDs = notebookUUIDs
        self.pageLimit = pageLimit
    }

    enum CodingKeys: String, CodingKey {
        case notebookUUIDs = "notebook_uuids"
        case pageLimit = "page_limit"
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(notebookUUIDs, forKey: .notebookUUIDs)
        // Omitted means: keep the page limit already saved. Change it through settings.
        try c.encodeIfPresent(pageLimit, forKey: .pageLimit)
    }
}

// MARK: - Settings

/// Environment as reported in `/api/v2/settings` (no dashboard URL there).
public struct EnvironmentSetting: Codable, Equatable, Sendable {
    public var name: EnvironmentName
    public var apiURL: String

    public init(name: EnvironmentName, apiURL: String) {
        self.name = name
        self.apiURL = apiURL
    }

    enum CodingKeys: String, CodingKey {
        case name
        case apiURL = "api_url"
    }
}

public struct AppSettings: Codable, Equatable, Sendable {
    public var pageLimit: Int?
    public var sourceDirectory: String?
    public var environment: EnvironmentSetting
    /// Preset name (`production`, `staging`) to API URL.
    public var environmentPresets: [String: String]

    public init(pageLimit: Int? = nil, sourceDirectory: String?, environment: EnvironmentSetting,
                environmentPresets: [String: String]) {
        self.pageLimit = pageLimit
        self.sourceDirectory = sourceDirectory
        self.environment = environment
        self.environmentPresets = environmentPresets
    }

    enum CodingKeys: String, CodingKey {
        case pageLimit = "page_limit"
        case sourceDirectory = "source_directory"
        case environment
        case environmentPresets = "environment_presets"
    }
}

/// Body of `PUT /api/v2/settings`: any subset of fields. Only fields that are set are sent.
/// `pageLimit` is doubly optional: `nil` = leave unchanged, `.some(nil)` = clear the limit (JSON null),
/// `.some(n)` = set limit.
public struct SettingsUpdate: Codable, Equatable, Sendable {
    public var pageLimit: Int??
    public var sourceDirectory: String?
    public var environment: EnvironmentSetting?

    public init(pageLimit: Int?? = nil, sourceDirectory: String? = nil, environment: EnvironmentSetting? = nil) {
        self.pageLimit = pageLimit
        self.sourceDirectory = sourceDirectory
        self.environment = environment
    }

    enum CodingKeys: String, CodingKey {
        case pageLimit = "page_limit"
        case sourceDirectory = "source_directory"
        case environment
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if c.contains(.pageLimit) {
            pageLimit = .some(try c.decodeIfPresent(Int.self, forKey: .pageLimit))
        } else {
            pageLimit = nil
        }
        sourceDirectory = try c.decodeIfPresent(String.self, forKey: .sourceDirectory)
        environment = try c.decodeIfPresent(EnvironmentSetting.self, forKey: .environment)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        if let limit = pageLimit { try c.encode(limit, forKey: .pageLimit) }
        try c.encodeIfPresent(sourceDirectory, forKey: .sourceDirectory)
        try c.encodeIfPresent(environment, forKey: .environment)
    }
}

public struct SettingsUpdateResult: Codable, Equatable, Sendable {
    public var ok: Bool
    public var needsSignIn: Bool

    public init(ok: Bool = true, needsSignIn: Bool = false) {
        self.ok = ok
        self.needsSignIn = needsSignIn
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? true
        needsSignIn = try c.decodeIfPresent(Bool.self, forKey: .needsSignIn) ?? false
    }

    enum CodingKeys: String, CodingKey {
        case ok
        case needsSignIn = "needs_sign_in"
    }
}

// MARK: - Deleted notebooks

/// A notebook deleted on the server. The contract says "same data as the legacy routes": legacy items carry
/// `notebook_uuid` (or `uuid`), `visible_name` (or `name`) and `deleted_at`; all are accepted.
public struct DeletedNotebook: Codable, Equatable, Sendable, Identifiable {
    public var uuid: String
    public var name: String
    public var deletedAt: Date?

    public var id: String { uuid }

    public init(uuid: String, name: String, deletedAt: Date? = nil) {
        self.uuid = uuid
        self.name = name
        self.deletedAt = deletedAt
    }

    enum CodingKeys: String, CodingKey {
        case notebookUUID = "notebook_uuid"
        case uuid
        case visibleName = "visible_name"
        case name
        case deletedAt = "deleted_at"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let u = try c.decodeIfPresent(String.self, forKey: .notebookUUID) {
            uuid = u
        } else {
            uuid = try c.decode(String.self, forKey: .uuid)
        }
        if let n = try c.decodeIfPresent(String.self, forKey: .visibleName) {
            name = n
        } else {
            name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        }
        deletedAt = try c.decodeIfPresent(Date.self, forKey: .deletedAt)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(uuid, forKey: .notebookUUID)
        try c.encode(name, forKey: .visibleName)
        try c.encodeIfPresent(deletedAt, forKey: .deletedAt)
    }
}

struct DeletedNotebooksResponse: Codable {
    var deletedNotebooks: [DeletedNotebook]
    enum CodingKeys: String, CodingKey { case deletedNotebooks = "deleted_notebooks" }
}

struct DeletedNotebookActionRequest: Codable {
    var action: DeletedNotebookAction
}

// MARK: - Update check

public struct UpdateCheck: Codable, Equatable, Sendable {
    public var hasUpdate: Bool
    public var currentVersion: String
    public var latestVersion: String?
    public var downloadURL: String?

    public init(hasUpdate: Bool, currentVersion: String, latestVersion: String? = nil, downloadURL: String? = nil) {
        self.hasUpdate = hasUpdate
        self.currentVersion = currentVersion
        self.latestVersion = latestVersion
        self.downloadURL = downloadURL
    }

    enum CodingKeys: String, CodingKey {
        case hasUpdate = "has_update"
        case currentVersion = "current_version"
        case latestVersion = "latest_version"
        case downloadURL = "download_url"
    }
}

// MARK: - Error body

struct APIErrorEnvelope: Decodable {
    struct Body: Decodable {
        var code: LocalAPIErrorCode
        var detail: String?
    }
    var error: Body
}
