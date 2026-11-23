import XCTest
@testable import RMirrorKit

/// Talks to a real, running core. Skipped unless RMIRROR_LIVE_PORT and RMIRROR_LIVE_TOKEN are set.
/// Start one with a throwaway HOME and config, for example:
///   (printf '%s\\n' "$TOKEN"; sleep 600) | RMIRROR_CONFIG_PATH=$TMP/config.yaml HOME=$TMP rmirror-core --headless
final class LiveCoreTests: XCTestCase {
    private func client() throws -> LocalAPIClient {
        let environment = ProcessInfo.processInfo.environment
        guard let portText = environment["RMIRROR_LIVE_PORT"], let port = Int(portText),
              let token = environment["RMIRROR_LIVE_TOKEN"] else {
            throw XCTSkip("no live core configured")
        }
        return LocalAPIClient(port: port, appToken: token)
    }

    func testEveryReadEndpointDecodes() async throws {
        let api = try client()
        let healthy = try await api.health()
        XCTAssertTrue(healthy)

        let state = try await api.state()
        XCTAssertEqual(state.apiVersion, 2)
        XCTAssertFalse(state.auth.signedIn, "the throwaway core has no sign-in")
        XCTAssertEqual(state.auth.state, .signedOut)
        if case .unknown(let raw) = state.folder.state { XCTFail("unknown folder state \(raw)") }
        if case .unknown(let raw) = state.watcher.state { XCTFail("unknown watcher state \(raw)") }
        if case .unknown(let raw) = state.sync.state { XCTFail("unknown sync state \(raw)") }
        if case .unknown(let raw) = state.environment.name { XCTFail("unknown environment \(raw)") }

        _ = try await api.notebooks()
        _ = try await api.syncProgress()
        let settings = try await api.settings()
        XCTAssertFalse(settings.environmentPresets.isEmpty)
        _ = try await api.deletedNotebooks()

        let suggestion = try await api.firstRunSuggestion(max: 3)
        XCTAssertEqual(suggestion.reason, .notSignedIn)
        XCTAssertTrue(suggestion.notebooks.isEmpty)
    }

    func testBeginSignInGivesAOneTimeLinkToThisCore() async throws {
        let api = try client()
        let url = try await api.beginSignIn()
        XCTAssertEqual(url.host, "127.0.0.1")
        XCTAssertEqual(url.path, "/auth/bridge")
        XCTAssertTrue(url.query?.hasPrefix("ticket=") ?? false)
    }

    func testOldUnprotectedRoutesAreGone() async throws {
        let api = try client()
        for path in ["/api/status", "/api/config", "/"] {
            let (_, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:\(api.port)\(path)")!)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 404, path)
        }
    }

    func testWrongTokenIsRejected() async throws {
        let good = try client()
        let bad = LocalAPIClient(port: good.port, appToken: String(repeating: "0", count: 64))
        do {
            _ = try await bad.state()
            XCTFail("expected a rejection")
        } catch let error as LocalAPIError {
            guard case .api(let code, let status, _) = error else { return XCTFail("got \(error)") }
            XCTAssertEqual(code, .badAppToken)
            XCTAssertEqual(status, 401)
        }
    }

    func testStartSyncWhileSignedOutIsRefused() async throws {
        do {
            try await client().startSync(notebookUUIDs: nil, pageLimit: nil)
            XCTFail("expected not_signed_in")
        } catch let error as LocalAPIError {
            guard case .api(let code, let status, _) = error else { return XCTFail("got \(error)") }
            XCTAssertEqual(code, .notSignedIn)
            XCTAssertEqual(status, 401)
        }
    }

    func testSettingsRoundTripKeepsPageLimitSemantics() async throws {
        let api = try client()
        _ = try await api.updateSettings(SettingsUpdate(pageLimit: .some(25)))
        var settings = try await api.settings()
        XCTAssertEqual(settings.pageLimit, 25)
        _ = try await api.updateSettings(SettingsUpdate(pageLimit: .some(nil)))
        settings = try await api.settings()
        XCTAssertNil(settings.pageLimit)
    }
}
