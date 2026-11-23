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
        timing.restartBackoff = [0.05]
        timing.terminateGrace = 2
        return timing
    }

    private func supervisor(_ url: URL, timing: CoreSupervisorTiming? = nil,
                            log: LogRecorder = LogRecorder()) -> (CoreSupervisor, StatusRecorder) {
        let recorder = StatusRecorder()
        let supervisor = CoreSupervisor(
            spec: CoreLaunchSpec(executableURL: url, arguments: [], port: 5999),
            timing: timing ?? fastTiming(),
            callbackQueue: DispatchQueue(label: "test-callbacks"),
            log: { log.append($0) }
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

    func testTheTokenArrivesAsTheFirstLineOnStdin() throws {
        let out = directory.appendingPathComponent("token.txt")
        let url = try script("read -r TOKEN\nprintf '%s' \"$TOKEN\" > '\(out.path)'\necho 'RMIRROR_CORE_READY port=5999 api=2'\ncat >/dev/null")
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

    // MARK: Environment

    func testChildDoesNotInheritArbitraryParentVariables() throws {
        setenv("RMIRROR_TEST_PARENT_SECRET", "must-not-leak", 1)
        defer { unsetenv("RMIRROR_TEST_PARENT_SECRET") }
        let out = directory.appendingPathComponent("env.txt")
        let url = try script("/usr/bin/env > '\(out.path)'\necho 'RMIRROR_CORE_READY port=5999 api=2'\ncat >/dev/null")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        let status = try XCTUnwrap(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        guard case .running(let connection) = status else { return XCTFail("not running") }
        let lines = try String(contentsOf: out, encoding: .utf8).split(separator: "\n").map(String.init)
        XCTAssertFalse(lines.contains { $0.hasPrefix("RMIRROR_TEST_PARENT_SECRET=") }, "parent variable leaked to the core")
        XCTAssertFalse(lines.contains { $0.hasPrefix("RMIRROR_APP_TOKEN=") }, "the token must not be in the environment")
        XCTAssertFalse(lines.contains { $0.contains(connection.appToken) })
        XCTAssertTrue(lines.contains("PYTHONUNBUFFERED=1"))
        XCTAssertTrue(lines.contains { $0.hasPrefix("HOME=") })
        supervisor.stopAndWait()
    }

    func testChildEnvironmentIsAnAllowlist() {
        let parent = [
            "HOME": "/Users/x", "PATH": "/usr/bin", "LANG": "en_GB.UTF-8", "SECRET": "s",
            "RMIRROR_CONFIG_PATH": "/tmp/evil.yaml", "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            "DYLD_INSERT_LIBRARIES": "/tmp/x.dylib", "RMIRROR_APP_TOKEN": "parent-token",
        ]
        let release = CoreSupervisor.childEnvironment(parent: parent, extra: ["EXTRA": "1"], development: false)
        XCTAssertEqual(release, ["HOME": "/Users/x", "PATH": "/usr/bin", "LANG": "en_GB.UTF-8",
                                 "EXTRA": "1", "PYTHONUNBUFFERED": "1"])
        let debug = CoreSupervisor.childEnvironment(parent: parent, extra: [:], development: true)
        XCTAssertEqual(debug["RMIRROR_CONFIG_PATH"], "/tmp/evil.yaml")
        XCTAssertEqual(debug["PYTHON_KEYRING_BACKEND"], "keyring.backends.null.Keyring")
        XCTAssertNil(debug["SECRET"])
        XCTAssertNil(debug["DYLD_INSERT_LIBRARIES"])
        XCTAssertNil(debug["RMIRROR_APP_TOKEN"], "a token in the parent's environment is never passed on")
        XCTAssertNil(release["RMIRROR_APP_TOKEN"])
    }

    #if DEBUG
    func testDevelopmentOverrideInDebugBuilds() throws {
        let spec = try XCTUnwrap(CoreLocator.launchSpec(
            bundle: Bundle(for: CoreSupervisorTests.self),
            environment: ["RMIRROR_CORE_CMD": "/usr/bin/python3", "RMIRROR_CORE_ARGS": "-m app.main --headless",
                          "RMIRROR_CORE_CWD": "/tmp"]))
        XCTAssertEqual(spec.executableURL.path, "/usr/bin/python3")
        XCTAssertEqual(spec.arguments, ["-m", "app.main", "--headless"])
        XCTAssertEqual(spec.workingDirectory?.path, "/tmp")
    }
    #endif

    // MARK: Stopping

    func testQuitDuringRestartDoesNotLaunchANewCore() throws {
        // The old core takes a moment to go after its stdin closes, so the restart is still
        // waiting for it when the app quits.
        let count = directory.appendingPathComponent("count.txt")
        let url = try script("""
        trap '' TERM
        echo run >> '\(count.path)'
        echo 'RMIRROR_CORE_READY port=5999 api=2'
        cat >/dev/null
        sleep 0.4
        """)
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        supervisor.restart()
        supervisor.stopAndWait()
        Thread.sleep(forTimeInterval: 0.8)
        let runs = try String(contentsOf: count, encoding: .utf8).split(separator: "\n").count
        XCTAssertEqual(runs, 1, "a core was launched after quit")
        XCTAssertEqual(supervisor.currentStatus, .stopped)
    }

    func testRestartLaunchesAfterTheOldCoreHasGone() throws {
        let count = directory.appendingPathComponent("count.txt")
        let url = try script("echo run >> '\(count.path)'\necho 'RMIRROR_CORE_READY port=5999 api=2'\ncat >/dev/null")
        let (supervisor, recorder) = supervisor(url)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        supervisor.restart()
        let deadline = Date().addingTimeInterval(5)
        var runs = 0
        while Date() < deadline {
            runs = (try? String(contentsOf: count, encoding: .utf8))?.split(separator: "\n").count ?? 0
            if runs >= 2, case .running = supervisor.currentStatus { break }
            Thread.sleep(forTimeInterval: 0.05)
        }
        XCTAssertEqual(runs, 2)
        supervisor.stopAndWait()
    }

    func testStopAndWaitKillsAHungCoreAfterTheQuitGrace() throws {
        // Ignores SIGTERM and stdin EOF: only SIGKILL ends it.
        let url = try script("trap '' TERM\necho 'RMIRROR_CORE_READY port=5999 api=2'\nexec 0<&-\nwhile :; do sleep 0.05; done")
        var timing = fastTiming()
        timing.quitGrace = 0.3
        let (supervisor, recorder) = supervisor(url, timing: timing)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { if case .running = $0 { return true } else { return false } })
        let started = Date()
        supervisor.stopAndWait()
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5)
        XCTAssertEqual(supervisor.currentStatus, .stopped)
    }

    // MARK: stderr

    func testStderrTailIsLoggedWhenTheCoreFails() throws {
        let url = try script("echo 'Traceback: something broke' >&2\nexit 1")
        var timing = fastTiming()
        timing.maxFailures = 0
        let log = LogRecorder()
        let (supervisor, recorder) = supervisor(url, timing: timing, log: log)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .failed(.crashLoop(lastExitCode: 1)) })
        XCTAssertNotNil(log.waitFor { $0.contains("Traceback: something broke") })
    }

    func testStderrContainingTheTokenIsNotLogged() throws {
        let url = try script("read -r TOKEN\necho \"leaked $TOKEN\" >&2\nexit 1")
        var timing = fastTiming()
        timing.maxFailures = 0
        let log = LogRecorder()
        let (supervisor, recorder) = supervisor(url, timing: timing, log: log)
        supervisor.start()
        XCTAssertNotNil(recorder.waitFor { $0 == .failed(.crashLoop(lastExitCode: 1)) })
        XCTAssertNotNil(log.waitFor { $0.contains("withheld") })
        XCTAssertFalse(log.all.contains { $0.contains("leaked") })
    }

    func testBoundedTailKeepsOnlyTheEnd() {
        let tail = BoundedTail(capacity: 8)
        tail.append(Data("0123456789".utf8))
        XCTAssertEqual(tail.text, "23456789")
        tail.append(Data("ab".utf8))
        XCTAssertEqual(tail.text, "456789ab")
        XCTAssertEqual(CoreSupervisor.stderrTailBytes, 4096)
        XCTAssertEqual(CoreSupervisorTiming().readyTimeout, 90)
        XCTAssertEqual(CoreSupervisorTiming().quitGrace, 3)
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

final class LogRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var lines: [String] = []

    func append(_ line: String) { lock.lock(); lines.append(line); lock.unlock() }
    var all: [String] { lock.lock(); defer { lock.unlock() }; return lines }

    func waitFor(timeout: TimeInterval = 5, _ predicate: (String) -> Bool) -> String? {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let match = all.first(where: predicate) { return match }
            Thread.sleep(forTimeInterval: 0.02)
        }
        return nil
    }
}
