import Foundation

/// How to start the core process. In a shipped app this is the bundled `rmirror-core`;
/// in a debug build it can be any command (see `CoreLocator`).
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

    public init(port: Int, appToken: String) {
        self.port = port
        self.appToken = appToken
    }
}

public struct CoreSupervisorTiming: Sendable {
    /// The first launch of a freshly notarized core can be slow while macOS scans it.
    public var readyTimeout: TimeInterval = 90
    public var restartBackoff: [TimeInterval] = [1, 2, 5, 15, 30]
    /// More than `maxFailures` unexpected exits within `failureWindow` stops the restart loop.
    public var maxFailures = 5
    public var failureWindow: TimeInterval = 120
    /// SIGTERM → SIGKILL grace while the app keeps running (restart, ready timeout).
    public var terminateGrace: TimeInterval = 8
    /// SIGTERM → SIGKILL grace when the app quits. The core exits within about a second of its
    /// stdin closing, so this only matters for a core that hangs; quitting must never hang.
    public var quitGrace: TimeInterval = 3
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
    /// The last bytes of the core's stderr kept for the system log when it fails.
    public static let stderrTailBytes = 4 * 1024

    private let spec: CoreLaunchSpec
    private let timing: CoreSupervisorTiming
    private let queue = DispatchQueue(label: "io.rmirror.core-supervisor")
    private let callbackQueue: DispatchQueue
    private let log: @Sendable (String) -> Void

    // All state below is confined to `queue`.
    private var status: CoreStatus = .stopped
    private var process: Process?
    private var stdinPipe: Pipe?
    /// Children asked to stop that may not have exited yet.
    private var exitingChildren: [Process] = []
    private var generation = 0
    private var wantRunning = false
    private var failureTimes: [Date] = []
    private var restartAttempt = 0
    private var stdoutBuffer = Data()
    private var stderrTail = BoundedTail(capacity: CoreSupervisor.stderrTailBytes)
    private var currentToken: String?
    private var onStatusChange: (@Sendable (CoreStatus) -> Void)?

    /// - Parameter log: where failure details go (default: the system log via `NSLog`).
    public init(
        spec: CoreLaunchSpec,
        timing: CoreSupervisorTiming = CoreSupervisorTiming(),
        callbackQueue: DispatchQueue = .main,
        log: @escaping @Sendable (String) -> Void = { NSLog("%@", $0) }
    ) {
        self.spec = spec
        self.timing = timing
        self.callbackQueue = callbackQueue
        self.log = log
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

    /// Stop and start again, for example after the user granted a permission. The new core is
    /// launched only once the old one has gone (it holds the port), and only if nobody asked
    /// to stop in the meantime: a quit during a restart never launches a new core.
    public func restart() {
        queue.async {
            self.wantRunning = true
            self.failureTimes.removeAll()
            self.restartAttempt = 0
            self.signalCurrentToStop()
            self.setStatus(.starting)
            self.launchWhenPreviousGone(
                generation: self.generation,
                killAt: Date().addingTimeInterval(self.timing.terminateGrace),
                giveUpAt: Date().addingTimeInterval(self.timing.terminateGrace + 2)
            )
        }
    }

    /// Stops the core and returns once it has exited, or was killed after `timing.quitGrace`.
    /// Safe to call from `applicationWillTerminate`: it never spins the run loop and returns
    /// within about `quitGrace` + 1 s.
    public func stopAndWait() {
        queue.sync {
            self.wantRunning = false
            self.signalCurrentToStop()
            self.waitForExitingChildren(grace: self.timing.quitGrace)
            self.setStatus(.stopped)
        }
    }

    // MARK: - Environment

    /// True in debug builds, where the development override and its pass-through variables apply.
    public static var isDebugBuild: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    /// Parent variables the core may see. Everything else in the app's environment stays out,
    /// so for example a `RMIRROR_CONFIG_PATH` set with `launchctl setenv` cannot redirect a
    /// release build's core.
    public static let inheritedVariables = [
        "HOME", "PATH", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "SHELL",
        "__CF_USER_TEXT_ENCODING",
    ]

    /// Passed through as well in debug builds only (running the core from source, live tests).
    public static let developmentVariables = ["RMIRROR_CONFIG_PATH", "PYTHON_KEYRING_BACKEND"]

    /// The child's whole environment: the allowlisted parent variables, the spec's extras, the
    /// launch token and unbuffered Python output.
    public static func childEnvironment(
        parent: [String: String],
        token: String,
        extra: [String: String],
        development: Bool = CoreSupervisor.isDebugBuild
    ) -> [String: String] {
        var environment: [String: String] = [:]
        let allowed = inheritedVariables + (development ? developmentVariables : [])
        for key in allowed {
            if let value = parent[key] { environment[key] = value }
        }
        for (key, value) in extra { environment[key] = value }
        environment["RMIRROR_APP_TOKEN"] = token
        environment["PYTHONUNBUFFERED"] = "1"
        return environment
    }

    // MARK: - Launch

    private func launch() {
        dispatchPrecondition(condition: .onQueue(queue))
        generation += 1
        let launchGeneration = generation
        stdoutBuffer.removeAll()
        let tail = BoundedTail(capacity: CoreSupervisor.stderrTailBytes)
        stderrTail = tail

        guard FileManager.default.isExecutableFile(atPath: spec.executableURL.path) else {
            setStatus(.failed(.cannotLaunch("not found: \(spec.executableURL.path)")))
            wantRunning = false
            return
        }

        let token = AppToken.generate()
        currentToken = token
        let child = Process()
        child.executableURL = spec.executableURL
        child.arguments = spec.arguments
        child.currentDirectoryURL = spec.workingDirectory
        child.environment = CoreSupervisor.childEnvironment(
            parent: ProcessInfo.processInfo.environment, token: token, extra: spec.extraEnvironment)

        let stdin = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()
        child.standardInput = stdin
        child.standardOutput = stdout
        child.standardError = stderr

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard let self else { return }
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            self.queue.async { self.consumeStdout(data, generation: launchGeneration, token: token) }
        }
        // Drained for the core's whole life so a write can never block it; only the last few KB are kept.
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            tail.append(data)
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
            stderr.fileHandleForReading.readabilityHandler = nil
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
            self.logStderrTail(self.stderrTail, token: self.currentToken, reason: "did not become ready")
            self.signalCurrentToStop()
            self.killExitingChildren(after: self.timing.terminateGrace)
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
        // stderr may still be arriving through its pipe; read the tail a moment later.
        let tail = stderrTail
        let token = currentToken
        queue.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.logStderrTail(tail, token: token, reason: "exited with status \(code)")
        }
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

    /// Writes the end of the core's stderr to the system log. The launch token only ever travels
    /// in the child's environment and the core never prints it; if the tail contains it anyway,
    /// the tail is withheld.
    private func logStderrTail(_ tail: BoundedTail, token: String?, reason: String) {
        let text = tail.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            log("rMirror: the core \(reason); it wrote nothing to stderr")
            return
        }
        if let token, !token.isEmpty, text.contains(token) {
            log("rMirror: the core \(reason); its stderr is withheld because it contains the launch token")
            return
        }
        log("rMirror: the core \(reason); last stderr output:\n\(text)")
    }

    // MARK: - Stopping

    /// Asks the current child to stop: stdin closed (the core exits on EOF) and SIGTERM.
    /// Returns at once; the child is remembered in `exitingChildren` until it has gone.
    private func signalCurrentToStop() {
        dispatchPrecondition(condition: .onQueue(queue))
        generation += 1  // exit of this child is expected: ignore it in handleExit
        exitingChildren.removeAll { !$0.isRunning }
        guard let child = process else { return }
        process = nil
        // Closing stdin is the second, independent stop signal for the core.
        try? stdinPipe?.fileHandleForWriting.close()
        stdinPipe = nil
        guard child.isRunning else { return }
        child.terminate()
        exitingChildren.append(child)
    }

    /// Blocks the supervisor queue (and its caller) until every child asked to stop has gone, or
    /// kills the rest after `grace`. Polls with short sleeps: never runs the caller's run loop.
    private func waitForExitingChildren(grace: TimeInterval) {
        dispatchPrecondition(condition: .onQueue(queue))
        let deadline = Date().addingTimeInterval(grace)
        while exitingChildren.contains(where: \.isRunning) && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        for child in exitingChildren where child.isRunning {
            kill(child.processIdentifier, SIGKILL)
        }
        // SIGKILL cannot be ignored; allow a moment for the exit to be noticed, but never wait long.
        let killDeadline = Date().addingTimeInterval(1)
        while exitingChildren.contains(where: \.isRunning) && Date() < killDeadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        exitingChildren.removeAll()
    }

    /// Kills, after `delay`, any child asked to stop that is still running. Does not block.
    private func killExitingChildren(after delay: TimeInterval) {
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            for child in self.exitingChildren where child.isRunning {
                kill(child.processIdentifier, SIGKILL)
            }
            self.exitingChildren.removeAll { !$0.isRunning }
        }
    }

    /// Part of `restart()`: polls until the old child has gone without blocking the queue, so a
    /// `stopAndWait()` can run meanwhile. Launches only if the restart is still wanted.
    private func launchWhenPreviousGone(generation expected: Int, killAt: Date, giveUpAt: Date) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard wantRunning, expected == generation else { return }
        exitingChildren.removeAll { !$0.isRunning }
        let now = Date()
        if exitingChildren.isEmpty || now >= giveUpAt {
            launch()
            return
        }
        if now >= killAt {
            for child in exitingChildren where child.isRunning { kill(child.processIdentifier, SIGKILL) }
        }
        queue.asyncAfter(deadline: .now() + 0.05) { [weak self] in
            self?.launchWhenPreviousGone(generation: expected, killAt: killAt, giveUpAt: giveUpAt)
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

/// The last `capacity` bytes written to it. Thread-safe.
public final class BoundedTail: @unchecked Sendable {
    public let capacity: Int
    private let lock = NSLock()
    private var buffer = Data()

    public init(capacity: Int) {
        self.capacity = max(1, capacity)
    }

    public func append(_ data: Data) {
        lock.lock()
        defer { lock.unlock() }
        buffer.append(data)
        if buffer.count > capacity { buffer = Data(buffer.suffix(capacity)) }
    }

    public var data: Data {
        lock.lock()
        defer { lock.unlock() }
        return buffer
    }

    /// The tail as text; bytes cut in the middle of a character are replaced, never fatal.
    public var text: String { String(decoding: data, as: UTF8.self) }
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
    /// The core bundled at `Contents/Resources/core/rmirror-core`. In debug builds only, a
    /// development override: `RMIRROR_CORE_CMD` is an executable path, `RMIRROR_CORE_ARGS` its
    /// space-separated arguments, `RMIRROR_CORE_CWD` its working directory. A release build
    /// ignores these variables and can only ever start the bundled core.
    public static func launchSpec(
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        port: Int = 5555
    ) -> CoreLaunchSpec? {
        #if DEBUG
        if let override = developmentOverride(environment: environment, port: port) { return override }
        #endif
        guard let resources = bundle.resourceURL else { return nil }
        let bundled = resources.appendingPathComponent("core/rmirror-core")
        guard FileManager.default.isExecutableFile(atPath: bundled.path) else { return nil }
        return CoreLaunchSpec(executableURL: bundled, port: port)
    }

    #if DEBUG
    static func developmentOverride(environment: [String: String], port: Int) -> CoreLaunchSpec? {
        guard let command = environment["RMIRROR_CORE_CMD"], !command.isEmpty else { return nil }
        let arguments = environment["RMIRROR_CORE_ARGS"]?
            .split(separator: " ").map(String.init) ?? ["--headless"]
        return CoreLaunchSpec(
            executableURL: URL(fileURLWithPath: command),
            arguments: arguments,
            workingDirectory: environment["RMIRROR_CORE_CWD"].map { URL(fileURLWithPath: $0) },
            port: port
        )
    }
    #endif
}
