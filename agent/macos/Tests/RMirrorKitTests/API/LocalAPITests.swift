import XCTest
@testable import RMirrorKit

final class LocalAPITests: XCTestCase {
    override func setUp() { StubURLProtocol.reset() }

    private func client() -> LocalAPIClient {
        LocalAPIClient(port: 5555, appToken: "secret-token", session: StubURLProtocol.makeSession())
    }

    private func stub(_ status: Int, _ body: String) {
        StubURLProtocol.handler = { _ in .init(status: status, body: body) }
    }

    private func stub(_ body: String) {
        let status = 200
        StubURLProtocol.handler = { _ in .init(status: status, body: body) }
    }

    private func lastBodyJSON() throws -> [String: Any] {
        let data = try XCTUnwrap(StubURLProtocol.bodies.last)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: Decoding

    static let progressJSON = """
    {"state": "running", "outcome": null,
     "counts": {"uploaded": 4, "failed": 0, "left_out_by_page_limit": 0, "will_retry": 0,
                "notebooks_done": 1, "notebooks_total": 3, "pages_total": 23},
     "started_at": "2026-11-23T08:00:00Z", "finished_at": null}
    """

    static let stateJSON = """
    {
      "api_version": 2, "core_version": "2.0.0",
      "auth": {"signed_in": true, "email": "user@example.com", "sign_in_required": false},
      "environment": {"name": "production", "api_url": "https://rmirror.io/api/v1", "dashboard_url": "https://rmirror.io"},
      "folder": {"path": "/Users/x/desktop", "state": "ok"},
      "watcher": {"state": "running", "observer_alive": true, "last_event_at": null, "last_rescan_at": "2026-11-23T08:00:00Z"},
      "queue": {"pending": 0, "running": true, "paused_reason": null},
      "quota": {"used": 4, "limit": 200, "remaining": 196, "reset_at": "2026-12-01T00:00:00Z", "fetched_at": "2026-11-23T08:00:00.123456Z"},
      "first_sync": {"completed": false},
      "sync": \(progressJSON),
      "last_upload_at": null
    }
    """

    func testDecodesState() async throws {
        stub(Self.stateJSON)
        let s = try await client().state()
        XCTAssertEqual(s.apiVersion, 2)
        XCTAssertEqual(s.coreVersion, "2.0.0")
        XCTAssertEqual(s.auth, AuthInfo(signedIn: true, email: "user@example.com", signInRequired: false))
        XCTAssertEqual(s.environment.name, .production)
        XCTAssertEqual(s.environment.dashboardURL, "https://rmirror.io")
        XCTAssertEqual(s.folder.state, .ok)
        XCTAssertEqual(s.watcher.state, .running)
        XCTAssertNil(s.watcher.lastEventAt)
        XCTAssertEqual(s.watcher.lastRescanAt, LocalAPICoding.parseDate("2026-11-23T08:00:00Z"))
        XCTAssertNil(s.queue.pausedReason)
        XCTAssertEqual(s.quota?.remaining, 196)
        XCTAssertNotNil(s.quota?.fetchedAt)
        XCTAssertFalse(s.firstSync.completed)
        XCTAssertEqual(s.sync.state, .running)
        XCTAssertEqual(s.sync.counts.pagesTotal, 23)
        XCTAssertNil(s.lastUploadAt)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.path, "/api/v2/state")
    }

    func testCatchUpIsOptionalAndUnknownValuesAreNotNeeded() async throws {
        // An older core sends no catch_up: nothing to wait for, no notice.
        stub(Self.stateJSON)
        var s = try await client().state()
        XCTAssertEqual(s.catchUp, CatchUpInfo(state: .notNeeded, unselectedOnServer: 0))

        let withCatchUp = Self.stateJSON.replacingOccurrences(
            of: "\"first_sync\": {\"completed\": false},",
            with: "\"first_sync\": {\"completed\": false}, \"catch_up\": {\"state\": \"pending\", \"unselected_on_server\": 0},")
        XCTAssertNotEqual(withCatchUp, Self.stateJSON)
        stub(withCatchUp)
        s = try await client().state()
        XCTAssertEqual(s.catchUp, CatchUpInfo(state: .pending, unselectedOnServer: 0))

        let decoder = LocalAPICoding.makeDecoder()
        func decode(_ json: String) throws -> CatchUpInfo { try decoder.decode(CatchUpInfo.self, from: Data(json.utf8)) }
        XCTAssertEqual(try decode(#"{"state": "done", "unselected_on_server": 12}"#), CatchUpInfo(state: .done, unselectedOnServer: 12))
        XCTAssertEqual(try decode(#"{"state": "unavailable", "unselected_on_server": 0}"#).state, .unavailable)
        XCTAssertEqual(try decode(#"{"state": "not_needed"}"#), CatchUpInfo(state: .notNeeded, unselectedOnServer: 0))
        XCTAssertEqual(try decode(#"{"state": "reticulating", "unselected_on_server": 3}"#).state, .notNeeded)
        XCTAssertEqual(try decode(#"{}"#), .notNeeded)
    }

    func testOnServerIsOptional() async throws {
        stub("""
        {"folder_state": "ok", "sync_all": false, "notebooks": [
          {"uuid": "u1", "name": "A", "folder_path": [], "document_type": "notebook", "page_count": 2,
           "selected": false, "synced_pages": 2, "on_server": true},
          {"uuid": "u2", "name": "B", "folder_path": [], "document_type": "notebook", "page_count": 1,
           "selected": false, "synced_pages": 0, "on_server": false},
          {"uuid": "u3", "name": "C", "folder_path": [], "document_type": "notebook", "page_count": 1,
           "selected": true, "synced_pages": 0}]}
        """)
        let r = try await client().notebooks()
        XCTAssertEqual(r.notebooks.map(\.onServer), [true, false, false])
    }

    func testDismissCatchUpPostsWithoutBody() async throws {
        stub(#"{"ok": true}"#)
        try await client().dismissCatchUp()
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/v2/catch-up/dismiss")
        XCTAssertEqual(req.value(forHTTPHeaderField: LocalAPIClient.tokenHeader), "secret-token")
    }

    func testDecodesNotebooks() async throws {
        stub("""
        {"folder_state": "ok", "sync_all": false, "notebooks": [
          {"uuid": "u1", "name": "Meeting Notes", "folder_path": ["Work", "2026"], "document_type": "notebook",
           "page_count": 12, "last_opened_at": "2026-11-20T10:00:00Z", "last_modified_at": "2026-11-20T10:05:00+00:00",
           "selected": true, "synced_pages": 12},
          {"uuid": "u2", "name": "Loose", "folder_path": [], "document_type": "pdf", "page_count": 1,
           "last_opened_at": null, "last_modified_at": null, "selected": false, "synced_pages": 0}]}
        """)
        let r = try await client().notebooks()
        XCTAssertEqual(r.notebooks.count, 2)
        XCTAssertEqual(r.notebooks[0].folderPath, ["Work", "2026"])
        XCTAssertEqual(r.notebooks[0].lastModifiedAt, LocalAPICoding.parseDate("2026-11-20T10:05:00Z"))
        XCTAssertNil(r.notebooks[1].lastOpenedAt)
        XCTAssertEqual(r.notebooks[1].id, "u2")
        // A core without folders: none, and no parent for each notebook.
        XCTAssertEqual(r.folders, [])
        XCTAssertNil(r.notebooks[0].parentUUID)
    }

    func testDecodesFoldersAndParents() async throws {
        stub("""
        {"folder_state": "ok", "sync_all": false,
         "folders": [{"uuid": "f1", "name": "Work", "parent_uuid": null},
                     {"uuid": "f2", "name": "2026", "parent_uuid": "f1"},
                     {"uuid": "f3", "name": "Empty"}],
         "notebooks": [
          {"uuid": "u1", "name": "Meeting Notes", "folder_path": ["Work", "2026"], "parent_uuid": "f2",
           "document_type": "notebook", "page_count": 12, "last_opened_at": null, "last_modified_at": null,
           "selected": true, "synced_pages": 12},
          {"uuid": "u2", "name": "Loose", "folder_path": [], "parent_uuid": null, "document_type": "notebook",
           "page_count": 1, "selected": false, "synced_pages": 0}]}
        """)
        let r = try await client().notebooks()
        XCTAssertEqual(r.folders, [FolderEntry(uuid: "f1", name: "Work"), FolderEntry(uuid: "f2", name: "2026", parentUUID: "f1"),
                                   FolderEntry(uuid: "f3", name: "Empty")])
        XCTAssertEqual(r.notebooks.map(\.parentUUID), ["f2", nil])
        XCTAssertNil(r.notebooks[1].lastOpenedAt, "a missing date key reads as no date")
    }

    func testDecodesSuggestionAndUnlimited() async throws {
        stub("""
        {"notebooks": [{"uuid": "u1", "name": "Meeting Notes", "page_count": 12}], "total_pages": 12,
         "quota": {"limit": -1, "remaining": null}, "reason": "ok"}
        """)
        let s = try await client().firstRunSuggestion(max: 5)
        XCTAssertEqual(s.totalPages, 12)
        XCTAssertEqual(s.quota, SuggestionQuota(limit: -1, remaining: nil))
        XCTAssertEqual(s.quota?.isUnlimited, true)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.query, "max=5")
    }

    func testUnlimitedQuotaInState() throws {
        let json = Self.stateJSON.replacingOccurrences(of: "\"used\": 4, \"limit\": 200, \"remaining\": 196",
                                                       with: "\"used\": 4, \"limit\": -1, \"remaining\": null")
        let s = try LocalAPICoding.makeDecoder().decode(AppState.self, from: Data(json.utf8))
        XCTAssertTrue(s.quota!.isUnlimited)
        XCTAssertNil(s.quota!.remaining)
        XCTAssertFalse(s.quota!.isExhausted)
    }

    func testNullQuotaAndNullTimestamps() throws {
        let json = Self.stateJSON
            .replacingOccurrences(of: #""quota": {"used": 4, "limit": 200, "remaining": 196, "reset_at": "2026-12-01T00:00:00Z", "fetched_at": "2026-11-23T08:00:00.123456Z"}"#,
                                  with: #""quota": null"#)
            .replacingOccurrences(of: #""last_rescan_at": "2026-11-23T08:00:00Z""#, with: #""last_rescan_at": null"#)
        let s = try LocalAPICoding.makeDecoder().decode(AppState.self, from: Data(json.utf8))
        XCTAssertNil(s.quota)
        XCTAssertNil(s.watcher.lastRescanAt)
        XCTAssertNil(s.lastUploadAt)
    }

    func testFractionalAndPlainTimestamps() {
        XCTAssertNotNil(LocalAPICoding.parseDate("2026-11-23T08:00:00Z"))
        XCTAssertNotNil(LocalAPICoding.parseDate("2026-11-23T08:00:00.5Z"))
        XCTAssertNotNil(LocalAPICoding.parseDate("2026-11-23T08:00:00.123456+00:00"))
        XCTAssertNotNil(LocalAPICoding.parseDate("2026-11-23T08:00:00"))
        XCTAssertNil(LocalAPICoding.parseDate("yesterday"))
    }

    func testUnknownEnumValuesDoNotFail() async throws {
        let json = Self.stateJSON
            .replacingOccurrences(of: "\"state\": \"ok\"", with: "\"state\": \"locked\"")
            .replacingOccurrences(of: "\"state\": \"running\", \"observer_alive\"", with: "\"state\": \"hibernating\", \"observer_alive\"")
            .replacingOccurrences(of: "\"paused_reason\": null", with: "\"paused_reason\": \"maintenance\"")
            .replacingOccurrences(of: "\"name\": \"production\"", with: "\"name\": \"lab\"")
            .replacingOccurrences(of: "\"outcome\": null", with: "\"outcome\": \"exploded\"")
        stub(json)
        let s = try await client().state()
        XCTAssertEqual(s.folder.state, .unknown("locked"))
        XCTAssertEqual(s.watcher.state, .unknown("hibernating"))
        XCTAssertEqual(s.queue.pausedReason, .unknown("maintenance"))
        XCTAssertEqual(s.environment.name, .unknown("lab"))
        XCTAssertEqual(s.sync.outcome, .unknown("exploded"))
        // and they round-trip
        let data = try JSONEncoder().encode(FolderState.unknown("locked"))
        XCTAssertEqual(String(data: data, encoding: .utf8), "\"locked\"")
        XCTAssertEqual(SuggestionReason(rawValue: "quota_exhausted"), .quotaExhausted)
        XCTAssertEqual(SuggestionReason(rawValue: "weird"), .unknown("weird"))
        XCTAssertEqual(SyncOutcome(rawValue: "stopped_sign_in"), .stoppedSignIn)
    }

    func testDecodesProgressWithNullPagesTotal() async throws {
        stub("""
        {"state": "done", "outcome": "partial",
         "counts": {"uploaded": 20, "failed": 3, "left_out_by_page_limit": 2, "will_retry": 1,
                    "notebooks_done": 3, "notebooks_total": 3, "pages_total": null},
         "started_at": "2026-11-23T08:00:00Z", "finished_at": "2026-11-23T08:05:00Z"}
        """)
        let p = try await client().syncProgress()
        XCTAssertEqual(p.outcome, .partial)
        XCTAssertNil(p.counts.pagesTotal)
        XCTAssertEqual(p.counts.leftOutByPageLimit, 2)
        XCTAssertEqual(p.counts.willRetry, 1)
        XCTAssertNotNil(p.finishedAt)
    }

    func testDecodesSettings() async throws {
        stub("""
        {"page_limit": null, "source_directory": "/Users/x/desktop",
         "environment": {"name": "production", "api_url": "https://rmirror.io/api/v1"},
         "environment_presets": {"production": "https://rmirror.io/api/v1", "staging": "https://staging.rmirror.io/api/v1"}}
        """)
        let s = try await client().settings()
        XCTAssertNil(s.pageLimit)
        XCTAssertEqual(s.environmentPresets["staging"], "https://staging.rmirror.io/api/v1")
        XCTAssertEqual(s.environment.apiURL, "https://rmirror.io/api/v1")
    }

    func testDecodesDeletedNotebooksAndUpdateCheck() async throws {
        stub(#"{"deleted_notebooks": [{"notebook_uuid": "abc", "visible_name": "Old", "deleted_at": "2026-11-01T00:00:00Z"}]}"#)
        let d = try await client().deletedNotebooks()
        XCTAssertEqual(d, [DeletedNotebook(uuid: "abc", name: "Old", deletedAt: LocalAPICoding.parseDate("2026-11-01T00:00:00Z"))])
        stub(#"{"has_update": false, "current_version": "2.0.0", "latest_version": "2.0.0", "download_url": null}"#)
        let u = try await client().updateCheck()
        XCTAssertFalse(u.hasUpdate)
        XCTAssertNil(u.downloadURL)
    }

    func testDecodingFailureMapsToDecodingError() async {
        stub(#"{"nonsense": true}"#)
        do {
            _ = try await client().state()
            XCTFail("expected throw")
        } catch let LocalAPIError.decoding(text) {
            XCTAssertFalse(text.isEmpty)
        } catch { XCTFail("wrong error \(error)") }
    }

    // MARK: Headers

    func testTokenHeaderOnV2AndHostHeader() async throws {
        stub(Self.progressJSON)
        _ = try await client().syncProgress()
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-RMirror-App-Token"), "secret-token")
        XCTAssertEqual(req.url?.absoluteString, "http://127.0.0.1:5555/api/v2/sync/progress")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Host"), "127.0.0.1:5555")
    }

    func testTokenHeaderAbsentOnHealth() async throws {
        stub("{\"status\": \"ok\"}")
        let ok = try await client().health()
        XCTAssertTrue(ok)
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertNil(req.value(forHTTPHeaderField: "X-RMirror-App-Token"))
        XCTAssertEqual(req.url?.path, "/health")
    }

    func testBeginSignInReturnsTheOneTimeLink() async throws {
        stub(#"{"url": "http://127.0.0.1:5555/auth/bridge?ticket=abc"}"#)
        let url = try await client().beginSignIn()
        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:5555/auth/bridge?ticket=abc")
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/v2/auth/begin")
        XCTAssertNotNil(req.value(forHTTPHeaderField: "X-RMirror-App-Token"))
    }

    func testBeginSignInRefusesALinkThatIsNotThisCore() async {
        for link in ["https://example.com/auth/bridge?ticket=abc", "http://127.0.0.1:9999/auth/bridge?ticket=abc",
                     "http://127.0.0.1:5555/other", "file:///etc/passwd", "http://localhost:5555/auth/bridge?ticket=abc"] {
            stub("{\"url\": \"\(link)\"}")
            do { _ = try await client().beginSignIn(); XCTFail("accepted \(link)") } catch {
                guard case LocalAPIError.decoding = error else { return XCTFail("got \(error)") }
            }
        }
    }

    // MARK: Errors

    func testErrorBodyMapping() async {
        let cases: [(String, Int, LocalAPIErrorCode)] = [
            ("bad_app_token", 401, .badAppToken), ("not_signed_in", 401, .notSignedIn),
            ("invalid_request", 400, .invalidRequest), ("sync_already_running", 409, .syncAlreadyRunning),
            ("core_not_ready", 503, .coreNotReady), ("cloud_timeout", 504, .cloudTimeout),
            ("cloud_error", 502, .cloudError), ("internal", 500, .internalError),
            ("brand_new_code", 418, .unknown("brand_new_code")),
        ]
        for (code, status, expected) in cases {
            stub(status, #"{"error": {"code": "\#(code)", "detail": "technical \#(code)"}}"#)
            do {
                _ = try await client().state()
                XCTFail("expected throw for \(code)")
            } catch {
                XCTAssertEqual(error as? LocalAPIError, .api(code: expected, status: status, detail: "technical \(code)"))
            }
        }
    }

    func testErrorWithoutDetailAndUnparseableBody() async {
        stub(409, #"{"error": {"code": "sync_already_running"}}"#)
        do { try await client().startSync(notebookUUIDs: nil, pageLimit: nil); XCTFail() } catch {
            XCTAssertEqual(error as? LocalAPIError, .api(code: .syncAlreadyRunning, status: 409, detail: nil))
        }
        stub(502, "<html>bad gateway</html>")
        do { _ = try await client().state(); XCTFail() } catch {
            XCTAssertEqual(error as? LocalAPIError, .api(code: .unknown("http_502"), status: 502, detail: nil))
        }
    }

    func testConnectionFailureMapsToCoreUnreachable() async {
        for code in [URLError.cannotConnectToHost, .timedOut, .networkConnectionLost] {
            StubURLProtocol.handler = { _ in throw URLError(code) }
            do { _ = try await client().state(); XCTFail() } catch {
                XCTAssertEqual(error as? LocalAPIError, .coreUnreachable)
            }
        }
        StubURLProtocol.handler = { _ in throw URLError(.cannotConnectToHost) }
        do { _ = try await client().health(); XCTFail() } catch {
            XCTAssertEqual(error as? LocalAPIError, .coreUnreachable)
        }
    }

    // MARK: Request bodies

    func testStartSyncBodies() async throws {
        stub(202, #"{"ok": true}"#)
        try await client().startSync(notebookUUIDs: ["a", "b"], pageLimit: 50)
        var req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/v2/sync/start")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Content-Type"), "application/json")
        var body = try lastBodyJSON()
        XCTAssertEqual(body["notebook_uuids"] as? [String], ["a", "b"])
        XCTAssertEqual(body["page_limit"] as? Int, 50)

        try await client().startSync(notebookUUIDs: nil, pageLimit: nil)
        req = try XCTUnwrap(StubURLProtocol.requests.last)
        body = try lastBodyJSON()
        XCTAssertNil(body["notebook_uuids"], "omitted when nil")
        XCTAssertFalse(body.keys.contains("page_limit"), "omitted, so the saved limit is kept")
        XCTAssertEqual(body.count, 0)
    }

    func testSetSelectionBody() async throws {
        stub(#"{"ok": true}"#)
        try await client().setSelection(syncAll: false, selectedNotebooks: ["x", "y"])
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "PUT")
        XCTAssertEqual(req.url?.path, "/api/v2/selection")
        let body = try lastBodyJSON()
        XCTAssertEqual(body["sync_all"] as? Bool, false)
        XCTAssertEqual(body["selected_notebooks"] as? [String], ["x", "y"])
        XCTAssertEqual(body.count, 2)
    }

    func testUpdateSettingsBodies() async throws {
        stub(#"{"ok": true, "needs_sign_in": true}"#)
        let r = try await client().updateSettings(SettingsUpdate(
            environment: EnvironmentSetting(name: .custom, apiURL: "https://example.test/api/v1")))
        XCTAssertTrue(r.needsSignIn)
        var req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "PUT")
        XCTAssertEqual(req.url?.path, "/api/v2/settings")
        var body = try lastBodyJSON()
        XCTAssertEqual(body.count, 1)
        let env = try XCTUnwrap(body["environment"] as? [String: String])
        XCTAssertEqual(env, ["name": "custom", "api_url": "https://example.test/api/v1"])

        // clear page limit -> explicit null, nothing else
        stub(#"{"ok": true, "needs_sign_in": false}"#)
        _ = try await client().updateSettings(SettingsUpdate(pageLimit: .some(nil)))
        body = try lastBodyJSON()
        XCTAssertEqual(body.count, 1)
        XCTAssertTrue(body["page_limit"] is NSNull)

        // set page limit + source directory
        _ = try await client().updateSettings(SettingsUpdate(pageLimit: 30, sourceDirectory: "/tmp/x"))
        body = try lastBodyJSON()
        XCTAssertEqual(body["page_limit"] as? Int, 30)
        XCTAssertEqual(body["source_directory"] as? String, "/tmp/x")
        XCTAssertEqual(body.count, 2)

        // empty update -> {}
        _ = try await client().updateSettings(SettingsUpdate())
        XCTAssertEqual(try lastBodyJSON().count, 0)
        req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertNotNil(req)
    }

    func testResolveDeletedNotebookAndPostsWithoutBody() async throws {
        stub(#"{"ok": true}"#)
        try await client().resolveDeletedNotebook(uuid: "abc-123", action: .resync)
        var req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/v2/deleted-notebooks/abc-123")
        XCTAssertEqual(try lastBodyJSON()["action"] as? String, "resync")
        try await client().resolveDeletedNotebook(uuid: "abc-123", action: .dismiss)
        XCTAssertEqual(try lastBodyJSON()["action"] as? String, "dismiss")

        try await client().resumeSync()
        req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.url?.path, "/api/v2/sync/resume")
        XCTAssertEqual(req.httpMethod, "POST")
        try await client().signOut()
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.path, "/api/v2/auth/sign-out")
    }

    // MARK: Mock and fixtures

    func testFixturesRoundTripThroughCoding() throws {
        let states = [Fixtures.signedOutState, Fixtures.signInRequiredState, Fixtures.folderMissingState,
                      Fixtures.folderUnreadableState, Fixtures.firstSyncPendingState, Fixtures.firstSyncRunningState,
                      Fixtures.readyState, Fixtures.quotaExhaustedState, Fixtures.syncDonePartialState,
                      Fixtures.catchingUpState, Fixtures.selectionNoticeState]
        for s in states {
            let data = try LocalAPICoding.makeEncoder().encode(s)
            XCTAssertEqual(try LocalAPICoding.makeDecoder().decode(AppState.self, from: data), s)
        }
        XCTAssertEqual(Fixtures.readyNotebooks.notebooks.count, 12)
        let library = try LocalAPICoding.makeEncoder().encode(Fixtures.libraryNotebooks)
        XCTAssertEqual(try LocalAPICoding.makeDecoder().decode(NotebooksResponse.self, from: library), Fixtures.libraryNotebooks)
        let caughtUp = try LocalAPICoding.makeEncoder().encode(Fixtures.catchUpLibraryNotebooks)
        XCTAssertEqual(try LocalAPICoding.makeDecoder().decode(NotebooksResponse.self, from: caughtUp),
                       Fixtures.catchUpLibraryNotebooks)
        XCTAssertEqual(Fixtures.threeNotebookSuggestion.totalPages, 23)
        XCTAssertTrue(Fixtures.quotaExhaustedState.quota!.isExhausted)
        XCTAssertEqual(Fixtures.firstSyncRunningState.sync.counts.uploaded, 4)
        XCTAssertEqual(Fixtures.syncDonePartialState.sync.outcome, .partial)
    }

    func testMockRecordsCallsAndReturnsConfiguredResults() async throws {
        let mock = MockLocalAPI()
        mock.stateResult = .success(Fixtures.signedOutState)
        let s = try await mock.state()
        XCTAssertFalse(s.auth.signedIn)
        mock.actionResult = .failure(.api(code: .notSignedIn, status: 401, detail: nil))
        do { try await mock.startSync(notebookUUIDs: ["a"], pageLimit: nil); XCTFail() } catch {
            XCTAssertEqual(error as? LocalAPIError, .api(code: .notSignedIn, status: 401, detail: nil))
        }
        XCTAssertEqual(mock.calls, [.state, .startSync(notebookUUIDs: ["a"], pageLimit: nil)])
        mock.failEverything(with: .coreUnreachable)
        do { _ = try await mock.notebooks(); XCTFail() } catch {
            XCTAssertEqual(error as? LocalAPIError, .coreUnreachable)
        }
    }
}
