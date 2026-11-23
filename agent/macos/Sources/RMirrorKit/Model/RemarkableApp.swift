import Foundation

/// The reMarkable desktop app on this Mac. rMirror reads the files it saves, so while it is not running
/// new pages from the tablet never arrive. It syncs fine while hidden in the background.
public enum RemarkableApp {
    public static let bundleIdentifier = "com.remarkable.desktop"

    /// Whether to warn that the reMarkable app is not running: only in normal use (`ready`). During
    /// onboarding, signed out, or with the folder missing or unreadable, the screen for that stage says
    /// what to do instead.
    public static func showsNotRunningWarning(stage: Stage, appRunning: Bool) -> Bool {
        stage == .ready && !appRunning
    }

    /// Whether to open the reMarkable app (hidden, in the background) as rMirror starts.
    /// - Parameter alreadyTried: rMirror already made this decision in this run.
    public static func opensAtStart(preferenceOn: Bool, appRunning: Bool, alreadyTried: Bool) -> Bool {
        preferenceOn && !appRunning && !alreadyTried
    }
}

/// Where the store learns whether the reMarkable app is running, and how it opens it.
/// The app uses an `NSWorkspace`-backed source; tests use `FakeRemarkableAppSource`.
@MainActor
public protocol RemarkableAppSource: AnyObject {
    /// Running in this login session right now.
    var isRunning: Bool { get }
    /// Installed on this Mac (macOS knows where to find it).
    var isInstalled: Bool { get }
    /// Starts reporting changes (the app launched or quit). Called once, by the store.
    func startObserving(_ onChange: @escaping @MainActor (Bool) -> Void)
    /// Opens the app. `inBackground`: hidden, without taking focus and without a recent-items entry.
    /// - Returns: false when the app is not installed.
    @discardableResult
    func open(inBackground: Bool) -> Bool
}

/// A `RemarkableAppSource` driven by hand, for tests and screenshots.
@MainActor
public final class FakeRemarkableAppSource: RemarkableAppSource {
    public private(set) var isRunning: Bool
    public var isInstalled: Bool
    /// Every `open` call, `true` for the background ones.
    public private(set) var openCalls: [Bool] = []
    private var onChange: (@MainActor (Bool) -> Void)?

    public init(isRunning: Bool = true, isInstalled: Bool = true) {
        self.isRunning = isRunning
        self.isInstalled = isInstalled
    }

    public func startObserving(_ onChange: @escaping @MainActor (Bool) -> Void) { self.onChange = onChange }

    @discardableResult
    public func open(inBackground: Bool) -> Bool {
        openCalls.append(inBackground)
        return isInstalled
    }

    /// The app launched (`true`) or quit (`false`), as the system would report it.
    public func simulate(running: Bool) {
        isRunning = running
        onChange?(running)
    }
}

/// rMirror's own choices about the reMarkable app, remembered between launches.
public struct RemarkableAppPreferences: Equatable, Sendable {
    /// Open the reMarkable app, hidden, when rMirror starts. Off unless the user turns it on.
    public var opensAtStart: Bool

    public init(opensAtStart: Bool = false) {
        self.opensAtStart = opensAtStart
    }

    static let opensAtStartKey = "remarkableApp.opensAtStart"

    public static func load(from defaults: UserDefaults) -> RemarkableAppPreferences {
        RemarkableAppPreferences(opensAtStart: defaults.bool(forKey: opensAtStartKey))
    }

    public func save(to defaults: UserDefaults) {
        defaults.set(opensAtStart, forKey: Self.opensAtStartKey)
    }
}
