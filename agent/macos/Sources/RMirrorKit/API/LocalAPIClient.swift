import Foundation

/// One async method per endpoint of the local API v2 (see `agent/docs/local-api.md`).
public protocol LocalAPI: Sendable {
    func state() async throws -> AppState
    func notebooks() async throws -> NotebooksResponse
    func setSelection(syncAll: Bool, selectedNotebooks: [String]) async throws
    func firstRunSuggestion(max: Int) async throws -> FirstRunSuggestion
    /// With `notebookUUIDs` the core saves them as the selection and starts; without, it syncs the current selection.
    /// `pageLimit` is always sent; nil means no limit.
    func startSync(notebookUUIDs: [String]?, pageLimit: Int?) async throws
    func syncProgress() async throws -> SyncProgress
    func resumeSync() async throws
    func settings() async throws -> AppSettings
    func updateSettings(_ update: SettingsUpdate) async throws -> SettingsUpdateResult
    /// Asks the core for a one-time sign-in link to open in the browser.
    func beginSignIn() async throws -> URL
    func signOut() async throws
    func deletedNotebooks() async throws -> [DeletedNotebook]
    func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async throws
    func updateCheck() async throws -> UpdateCheck
    /// `GET /health` (no token). True on a 2xx answer; throws `coreUnreachable` if nothing listens.
    func health() async throws -> Bool
}

extension LocalAPI {
    public func firstRunSuggestion() async throws -> FirstRunSuggestion {
        try await firstRunSuggestion(max: 3)
    }

    public func startSync() async throws {
        try await startSync(notebookUUIDs: nil, pageLimit: nil)
    }
}

public final class LocalAPIClient: LocalAPI, @unchecked Sendable {
    public static let tokenHeader = "X-RMirror-App-Token"

    public let port: Int
    private let appToken: String
    private let session: URLSession
    private let decoder = LocalAPICoding.makeDecoder()
    private let encoder = LocalAPICoding.makeEncoder()

    /// Where the user signs in (opened in the default browser).

    public init(port: Int, appToken: String, session: URLSession? = nil) {
        self.port = port
        self.appToken = appToken
        self.session = session ?? LocalAPIClient.makeDefaultSession()
    }

    /// Ephemeral session: no cache, no cookies, no proxy.
    public static func makeDefaultSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.httpCookieAcceptPolicy = .never
        config.connectionProxyDictionary = [:]
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }

    // MARK: Endpoints

    public func state() async throws -> AppState {
        try await get("/api/v2/state", timeout: 5)
    }

    public func notebooks() async throws -> NotebooksResponse {
        try await get("/api/v2/notebooks", timeout: 15)
    }

    public func setSelection(syncAll: Bool, selectedNotebooks: [String]) async throws {
        let _: OKResponse = try await send("PUT", "/api/v2/selection",
                                           body: SelectionRequest(syncAll: syncAll, selectedNotebooks: selectedNotebooks),
                                           timeout: 15)
    }

    public func firstRunSuggestion(max: Int) async throws -> FirstRunSuggestion {
        try await get("/api/v2/first-run/suggestion", query: [URLQueryItem(name: "max", value: String(max))], timeout: 15)
    }

    public func startSync(notebookUUIDs: [String]?, pageLimit: Int?) async throws {
        let _: OKResponse = try await send("POST", "/api/v2/sync/start",
                                           body: StartSyncRequest(notebookUUIDs: notebookUUIDs, pageLimit: pageLimit),
                                           timeout: 15)
    }

    public func syncProgress() async throws -> SyncProgress {
        try await get("/api/v2/sync/progress", timeout: 5)
    }

    public func resumeSync() async throws {
        let _: OKResponse = try await send("POST", "/api/v2/sync/resume", body: Optional<EmptyBody>.none, timeout: 15)
    }

    public func settings() async throws -> AppSettings {
        try await get("/api/v2/settings", timeout: 10)
    }

    public func updateSettings(_ update: SettingsUpdate) async throws -> SettingsUpdateResult {
        try await send("PUT", "/api/v2/settings", body: update, timeout: 15)
    }

    public func beginSignIn() async throws -> URL {
        let response: BeginSignInResponse = try await send("POST", "/api/v2/auth/begin", body: Optional<EmptyBody>.none, timeout: 15)
        // Only ever open a link back to this Mac's own core.
        guard let url = URL(string: response.url), url.scheme == "http", url.host == "127.0.0.1", url.port == port,
              url.path == "/auth/bridge" else {
            throw LocalAPIError.decoding("unexpected sign-in link")
        }
        return url
    }

    public func signOut() async throws {
        let _: OKResponse = try await send("POST", "/api/v2/auth/sign-out", body: Optional<EmptyBody>.none, timeout: 15)
    }

    public func deletedNotebooks() async throws -> [DeletedNotebook] {
        let response: DeletedNotebooksResponse = try await get("/api/v2/deleted-notebooks", timeout: 30)
        return response.deletedNotebooks
    }

    public func resolveDeletedNotebook(uuid: String, action: DeletedNotebookAction) async throws {
        let escaped = uuid.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? uuid
        let _: OKResponse = try await send("POST", "/api/v2/deleted-notebooks/\(escaped)",
                                           body: DeletedNotebookActionRequest(action: action), timeout: 30)
    }

    public func updateCheck() async throws -> UpdateCheck {
        try await get("/api/v2/update-check", timeout: 30)
    }

    public func health() async throws -> Bool {
        let request = makeRequest(method: "GET", path: "/health", query: [], timeout: 5, withToken: false)
        let (_, status) = try await perform(request)
        return (200..<300).contains(status)
    }

    // MARK: Plumbing

    private struct EmptyBody: Encodable {}

    private func makeRequest(method: String, path: String, query: [URLQueryItem], timeout: TimeInterval,
                             withToken: Bool) -> URLRequest {
        var components = URLComponents()
        components.scheme = "http"
        components.host = "127.0.0.1"
        components.port = port
        components.path = path
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.httpShouldHandleCookies = false
        request.setValue("127.0.0.1:\(port)", forHTTPHeaderField: "Host")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if withToken { request.setValue(appToken, forHTTPHeaderField: Self.tokenHeader) }
        return request
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], timeout: TimeInterval) async throws -> T {
        let request = makeRequest(method: "GET", path: path, query: query, timeout: timeout, withToken: true)
        return try await execute(request)
    }

    private func send<T: Decodable, B: Encodable>(_ method: String, _ path: String, body: B?,
                                                  timeout: TimeInterval) async throws -> T {
        var request = makeRequest(method: method, path: path, query: [], timeout: timeout, withToken: true)
        if let body {
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return try await execute(request)
    }

    private func perform(_ request: URLRequest) async throws -> (Data, Int) {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw LocalAPIError.coreUnreachable }
            return (data, http.statusCode)
        } catch let error as LocalAPIError {
            throw error
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            throw LocalAPIError.coreUnreachable
        }
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, status) = try await perform(request)
        guard (200..<300).contains(status) else {
            if let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data) {
                throw LocalAPIError.api(code: envelope.error.code, status: status, detail: envelope.error.detail)
            }
            throw LocalAPIError.api(code: .unknown("http_\(status)"), status: status, detail: nil)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw LocalAPIError.decoding(String(describing: error))
        }
    }
}
