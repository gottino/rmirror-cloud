import XCTest
@testable import RMirrorKit

/// Drives the supervisor with small shell scripts standing in for the core.
final class CoreSupervisorTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("rmirror-supervisor-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private func script(_ body: String) throws -> URL {
        let url = directory.appendingPathComponent("core-\(UUID().uuidString).sh")
        try "#!/bin/sh\n\(body)\n".write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return url
    }

    private func fastTiming() -> CoreSupervisorTiming {
        var timing = CoreSupervisorTiming()
        timing.healthPollInterval = 0.05
        timing.restartBackoff = [0.05]
        timing.terminateGrace = 2
        return timing
    }

    private func supervisor(_ url: URL, timing: CoreSupervisorTiming? = nil, healthy: Bool = false) -> (CoreSupervisor, StatusRecorder) {
        let recorder = StatusRecorder()
        let supervisor = CoreSupervisor(
            spec: CoreLaunchSpec(executableURL: url, arguments: [], port: 5999),
            timing: timing ?? fastTiming(),
            callbackQueue: DispatchQueue(label: "test-callbacks"),
            healthCheck: { _ in healthy }
        )
        supervisor.setStatusHandler { recorder.append($0) }
        return (supervisor, recorder)
    }

    func testReadyLineMakesItRunningWithThePortAndAToken() throws {
        let url = try script("echo 'RMIRROR_CORE_READY port=5123 api=2'\ncat >/dev/null")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        let status = try XCTUnwrap(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        guard case .running(let connection) = status else { return XCTFail("not running") }
        XCTAssertEqual(connection.port, 5123)
        XCTAssertEqual(connection.appToken.count, 64)
        supervisor.stopAndWait()
        XCTAssertEqual(supervisor.currentStatus, .stopped)
    }

    func testHealthCheckAloneMakesItRunning() throws {
        let url = try script("cat >/dev/null")
        let (supervisor, recorder) = supervisor(url, healthy: true)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .running(CoreConnection(port: 5999, appToken: "")) || { if case .running = $0 { return true } else { return false } }($0) })
        supervisor.stopAndWait()
    }

    func testTheTokenReachesTheChildEnvironment() throws {
        let out = directory.appendingPathComponent("token.txt")
        let url = try script("printf '%s' \"$RMIRROR_APP_TOKEN\" > '\(out.path)'\necho 'RMIRROR_CORE_READY port=5999 api=2'\ncat >/dev/null")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        let status = try XCTUnwrap(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        guard case .running(let connection) = status else { return XCTFail("not running") }
        XCTAssertEqual(try String(contentsOf: out, encoding: .utf8), connection.appToken)
        supervisor.stopAndWait()
    }

    func testChildSeesEndOfInputWhenStopped() throws {
        // The script ignores SIGTERM and only ends when its stdin closes, like a core whose
        // parent vanished. It must be gone after stopAndWait, well inside the grace period.
        let marker = directory.appendingPathComponent("eof.txt")
        let url = try script("trap '' TERM\necho 'RMIRROR_CORE_READY port=5999 api=2'\ncat >/dev/null\necho done > '\(marker.path)'")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        let started = Date()
        supervisor.stopAndWait()
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5, "should end on stdin EOF, not on the kill after the grace period")
        XCTAssertTrue(FileManager.default.fileExists(atPath: marker.path))
    }

    func testExitCodeThreeMeansPortInUseAndIsNotRetried() throws {
        let count = directory.appendingPathComponent("count.txt")
        let url = try script("echo run >> '\(count.path)'\nexit 3")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .failed(.portInUse) })
        Thread.sleep(forTimeInterval: 0.3)
        let runs = try String(contentsOf: count, encoding: .utf8).split(separator: "\n").count
        XCTAssertEqual(runs, 1)
    }

    func testUnexpectedExitIsRestarted() throws {
        let count = directory.appendingPathComponent("count.txt")
        let url = try script("""
        echo run >> '\(count.path)'
        if [ "$(wc -l < '\(count.path)' | tr -d ' ')" -lt 2 ]; then exit 1; fi
        echo 'RMIRROR_CORE_READY port=5999 api=2'
        cat >/dev/null
        """)
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        XCTAssertTrue(recorder.all.contains(.restarting(attempt: 1)))
        supervisor.stopAndWait()
    }

    func testCrashLoopStopsRetrying() throws {
        let url = try script("exit 1")
        var timing = fastTiming()
        timing.maxFailures = 2
        let (supervisor, recorder) = supervisor(url, timing: timing)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .failed(.crashLoop(lastExitCode: 1)) })
    }

    func testNeverReadyTimesOut() throws {
        let url = try script("cat >/dev/null")
        var timing = fastTiming()
        timing.readyTimeout = 0.3
        let (supervisor, recorder) = supervisor(url, timing: timing)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .failed(.readyTimeout) })
    }

    func testMissingExecutableFailsCleanly() {
        let (supervisor, recorder) = supervisor(directory.appendingPathComponent("nope"))
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .failed(.cannotLaunch) = $0 { return true } else { return false } })
    }

    func testReadyLinePortParsing() {
        XCTAssertEqual(CoreSupervisor.port(fromReadyLine: "RMIRROR_CORE_READY port=5555 api=2"), 5555)
        XCTAssertNil(CoreSupervisor.port(fromReadyLine: "RMIRROR_CORE_READY"))
    }
}

final class StatusRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var statuses: [CoreStatus] = []

    func append(_ status: CoreStatus) { lock.lock(); statuses.append(status); lock.unlock() }
    var all: [CoreStatus] { lock.lock(); defer { lock.unlock() }; return statuses }

    func waitFor(timeout: TimeInterval = 5, _ predicate: (CoreStatus) -> Bool) -> CoreStatus? {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let match = all.first(where: predicate) { return match }
            Thread.sleep(forTimeInterval: 0.02)
        }
        return nil
    }
}
