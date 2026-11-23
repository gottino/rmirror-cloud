import Foundation

/// How to start the core process. In a shipped app this is the bundled `rmirror-core`;
/// in development it can be any command (see `CoreLocator`).
public struct CoreLaunchSpec: Equatable, Sendable {
    public var executableURL: URL
    public var arguments: [String]
    public var workingDirectory: URL?
    public var extraEnvironment: [String: String]
    public var port: Int

    public init(
        executableURL: URL,
        arguments: [String] = ["--headless"],
        workingDirectory: URL? = nil,
        extraEnvironment: [String: String] = [:],
        port: Int = 5555
    ) {
        self.executableURL = executableURL
        self.arguments = arguments
        self.workingDirectory = workingDirectory
        self.extraEnvironment = extraEnvironment
        self.port = port
    }
}

public enum CoreFailure: Equatable, Sendable {
    /// Exit code 3: something else already listens on the port (usually another rMirror).
    case portInUse
    /// The executable is missing or could not be started.
    case cannotLaunch(String)
    /// Started but never became ready.
    case readyTimeout
    /// Kept crashing: too many unexpected exits in a short time.
    case crashLoop(lastExitCode: Int32)
}

public enum CoreStatus: Equatable, Sendable {
    case stopped
    case starting
    case running(CoreConnection)
    /// Waiting before the next start attempt after an unexpected exit.
    case restarting(attempt: Int)
    case failed(CoreFailure)
}

/// What the app needs to talk to a running core.
public struct CoreConnection: Equatable, Sendable {
    public let port: Int
    public let appToken: String
}

public struct CoreSupervisorTiming: Sendable {
    public var readyTimeout: TimeInterval = 30
    public var restartBackoff: [TimeInterval] = [1, 2, 5, 15, 30]
    /// More than `maxFailures` unexpected exits within `failureWindow` stops the restart loop.
    public var maxFailures = 5
    public var failureWindow: TimeInterval = 120
    public var terminateGrace: TimeInterval = 8
    public init() {}
}

/// Starts the Python core as a child process, waits until it is ready, restarts it if it
/// dies, and stops it on quit.
///
/// The child is a plain child process started with `Process`, which is what makes macOS
/// attribute its file access (Full Disk Access) to the app. Its stdin is a pipe whose write
/// end this object keeps open and never writes to: when the app goes away for any reason
/// the core sees end-of-file and shuts itself down, so it cannot be left behind holding the port.
public final class CoreSupervisor: @unchecked Sendable {
    public static let exitCodePortInUse: Int32 = 3
    public static let readyLinePrefix = "RMIRROR_CORE_READY"

    private let spec: CoreLaunchSpec
    private let timing: CoreSupervisorTiming
    private let queue = DispatchQueue(label: "io.rmirror.core-supervisor")
    private let callbackQueue: DispatchQueue

    // All state below is confined to `queue`.
    private var status: CoreStatus = .stopped
    private var process: Process?
    private var stdinPipe: Pipe?
    private var generation = 0
    private var wantRunning = false
    private var failureTimes: [Date] = []
    private var restartAttempt = 0
    private var stdoutBuffer = Data()
    private var onStatusChange: (@Sendable (CoreStatus) -> Void)?

    public init(
        spec: CoreLaunchSpec,
        timing: CoreSupervisorTiming = CoreSupervisorTiming(),
        callbackQueue: DispatchQueue = .main
    ) {
        self.spec = spec
        self.timing = timing
        self.callbackQueue = callbackQueue
    }

    /// Called on `callbackQueue` every time the status changes.
    public func setStatusHandler(_ handler: @escaping @Sendable (CoreStatus) -> Void) {
        queue.async { self.onStatusChange = handler }
    }

    public var currentStatus: CoreStatus { queue.sync { status } }

    public func start() {
        queue.async {
            guard !self.wantRunning else { return }
            self.wantRunning = true
            self.failureTimes.removeAll()
            self.restartAttempt = 0
            self.launch()
        }
    }

    /// Stop and start again, for example after the user granted a permission.
    public func restart() {
        queue.async {
            self.wantRunning = true
            self.failureTimes.removeAll()
            self.restartAttempt = 0
            self.terminateCurrent(waitForExit: true)
            self.launch()
        }
    }

    /// Stops the core and returns once it has exited (or was killed after the grace period).
    /// Safe to call from `applicationWillTerminate`.
    public func stopAndWait() {
        queue.sync {
            self.wantRunning = false
            self.terminateCurrent(waitForExit: true)
            self.setStatus(.stopped)
        }
    }

    // MARK: - Launch

    private func launch() {
        dispatchPrecondition(condition: .onQueue(queue))
        generation += 1
        let launchGeneration = generation
        stdoutBuffer.removeAll()

        guard FileManager.default.isExecutableFile(atPath: spec.executableURL.path) else {
            setStatus(.failed(.cannotLaunch("not found: \(spec.executableURL.path)")))
            wantRunning = false
            return
        }

        let token = AppToken.generate()
        let child = Process()
        child.executableURL = spec.executableURL
        child.arguments = spec.arguments
        child.currentDirectoryURL = spec.workingDirectory
        var environment = ProcessInfo.processInfo.environment
        for (key, value) in spec.extraEnvironment { environment[key] = value }
        environment["RMIRROR_APP_TOKEN"] = token
        environment["PYTHONUNBUFFERED"] = "1"
        child.environment = environment

        let stdin = Pipe()
        let stdout = Pipe()
        child.standardInput = stdin
        child.standardOutput = stdout
        child.standardError = FileHandle.nullDevice

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard let self else { return }
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            self.queue.async { self.consumeStdout(data, generation: launchGeneration, token: token) }
        }
        child.terminationHandler = { [weak self] finished in
            guard let self else { return }
            self.queue.async { self.handleExit(of: finished, generation: launchGeneration) }
        }

        setStatus(.starting)
        do {
            try child.run()
        } catch {
            stdout.fileHandleForReading.readabilityHandler = nil
            setStatus(.failed(.cannotLaunch(error.localizedDescription)))
            wantRunning = false
            return
        }
        process = child
        stdinPipe = stdin
        armReadyTimeout(generation: launchGeneration)
    }

    private func consumeStdout(_ data: Data, generation launchGeneration: Int, token: String) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard launchGeneration == generation else { return }
        stdoutBuffer.append(data)
        // Keep the buffer bounded; the core prints very little.
        if stdoutBuffer.count > 64 * 1024 { stdoutBuffer.removeFirst(stdoutBuffer.count - 16 * 1024) }
        guard case .starting = status,
              let text = String(data: stdoutBuffer, encoding: .utf8),
              let readyLine = text.split(whereSeparator: \.isNewline)
                  .first(where: { $0.hasPrefix(CoreSupervisor.readyLinePrefix) })
        else { return }
        markRunning(token: token, port: CoreSupervisor.port(fromReadyLine: String(readyLine)) ?? spec.port)
    }

    /// The only readiness signal is the ready line on the child's own stdout. A health request
    /// to the port is deliberately not used: if another process were listening there, it would
    /// answer, and the app would then send it the launch token.
    private func armReadyTimeout(generation launchGeneration: Int) {
        queue.asyncAfter(deadline: .now() + timing.readyTimeout) { [weak self] in
            guard let self, launchGeneration == self.generation, case .starting = self.status else { return }
            self.terminateCurrent(waitForExit: true)
            self.wantRunning = false
            self.setStatus(.failed(.readyTimeout))
        }
    }

    private func markRunning(token: String, port: Int) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard case .starting = status, process?.isRunning == true else { return }
        restartAttempt = 0
        setStatus(.running(CoreConnection(port: port, appToken: token)))
    }

    /// `RMIRROR_CORE_READY port=5555 api=2` → 5555
    static func port(fromReadyLine line: String) -> Int? {
        for field in line.split(separator: " ") where field.hasPrefix("port=") {
            return Int(field.dropFirst("port=".count))
        }
        return nil
    }

    // MARK: - Exit handling

    private func handleExit(of finished: Process, generation launchGeneration: Int) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard launchGeneration == generation, process === finished else { return }
        process = nil
        stdinPipe = nil
        guard wantRunning else {
            setStatus(.stopped)
            return
        }
        let code = finished.terminationStatus
        if finished.terminationReason == .exit, code == CoreSupervisor.exitCodePortInUse {
            wantRunning = false
            setStatus(.failed(.portInUse))
            return
        }

        let now = Date()
        failureTimes = failureTimes.filter { now.timeIntervalSince($0) < timing.failureWindow }
        failureTimes.append(now)
        if failureTimes.count > timing.maxFailures {
            wantRunning = false
            setStatus(.failed(.crashLoop(lastExitCode: code)))
            return
        }

        let delay = timing.restartBackoff[min(restartAttempt, timing.restartBackoff.count - 1)]
        restartAttempt += 1
        setStatus(.restarting(attempt: restartAttempt))
        let scheduledGeneration = generation
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, self.wantRunning, scheduledGeneration == self.generation else { return }
            self.launch()
        }
    }

    /// Asks the current child to stop (SIGTERM), then kills it after the grace period.
    private func terminateCurrent(waitForExit: Bool) {
        dispatchPrecondition(condition: .onQueue(queue))
        generation += 1  // exit of this child is expected: ignore it in handleExit
        guard let child = process else { return }
        process = nil
        // Closing stdin is the second, independent stop signal for the core.
        try? stdinPipe?.fileHandleForWriting.close()
        stdinPipe = nil
        guard child.isRunning else { return }
        child.terminate()
        guard waitForExit else { return }
        let deadline = Date().addingTimeInterval(timing.terminateGrace)
        while child.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
        if child.isRunning {
            kill(child.processIdentifier, SIGKILL)
            child.waitUntilExit()
        }
    }

    private func setStatus(_ newStatus: CoreStatus) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard newStatus != status else { return }
        status = newStatus
        if let handler = onStatusChange {
            callbackQueue.async { handler(newStatus) }
        }
    }
}

public enum AppToken {
    /// 32 random bytes as 64 hex characters.
    public static func generate() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let result = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if result != errSecSuccess {
            var generator = SystemRandomNumberGenerator()
            bytes = bytes.map { _ in UInt8.random(in: .min ... .max, using: &generator) }
        }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}

/// Finds the core to run.
public enum CoreLocator {
    /// Development override: `RMIRROR_CORE_CMD` is an executable path, `RMIRROR_CORE_ARGS` its
    /// space-separated arguments, `RMIRROR_CORE_CWD` its working directory.
    /// Otherwise the core bundled at `Contents/Resources/core/rmirror-core`.
    public static func launchSpec(
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        port: Int = 5555
    ) -> CoreLaunchSpec? {
        if let command = environment["RMIRROR_CORE_CMD"], !command.isEmpty {
            let arguments = environment["RMIRROR_CORE_ARGS"]?
                .split(separator: " ").map(String.init) ?? ["--headless"]
            return CoreLaunchSpec(
                executableURL: URL(fileURLWithPath: command),
                arguments: arguments,
                workingDirectory: environment["RMIRROR_CORE_CWD"].map { URL(fileURLWithPath: $0) },
                port: port
            )
        }
        guard let resources = bundle.resourceURL else { return nil }
        let bundled = resources.appendingPathComponent("core/rmirror-core")
        guard FileManager.default.isExecutableFile(atPath: bundled.path) else { return nil }
        return CoreLaunchSpec(executableURL: bundled, port: port)
    }
}
