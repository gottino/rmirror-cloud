import AppKit
import RMirrorKit

/// Whether the reMarkable desktop app runs in this login session, from `NSWorkspace`: the running
/// applications once, then the launch and quit notifications (no polling). An app running in another
/// macOS user account does not count, which is right: its files land in that account.
@MainActor
final class RemarkableAppWatcher: RemarkableAppSource {
    private let bundleIdentifier = RemarkableApp.bundleIdentifier
    private let workspace = NSWorkspace.shared
    private var observers: [NSObjectProtocol] = []
    private(set) var isRunning: Bool

    init() {
        isRunning = NSWorkspace.shared.runningApplications.contains {
            $0.bundleIdentifier == RemarkableApp.bundleIdentifier && !$0.isTerminated
        }
    }

    var isInstalled: Bool { applicationURL != nil }

    private var applicationURL: URL? { workspace.urlForApplication(withBundleIdentifier: bundleIdentifier) }

    func startObserving(_ onChange: @escaping @MainActor (Bool) -> Void) {
        guard observers.isEmpty else { return }
        let center = workspace.notificationCenter
        for name in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] note in
                guard let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                      app.bundleIdentifier == RemarkableApp.bundleIdentifier else { return }
                let launched = note.name == NSWorkspace.didLaunchApplicationNotification
                let pid = app.processIdentifier
                Task { @MainActor in
                    guard let self else { return }
                    self.isRunning = launched || self.anotherCopyRuns(besides: pid)
                    onChange(self.isRunning)
                }
            })
        }
    }

    /// After one copy quits, whether another one (rare) is still running.
    private func anotherCopyRuns(besides pid: pid_t) -> Bool {
        workspace.runningApplications.contains {
            $0.bundleIdentifier == bundleIdentifier && $0.processIdentifier != pid && !$0.isTerminated
        }
    }

    @discardableResult
    func open(inBackground: Bool) -> Bool {
        guard let url = applicationURL else { return false }
        let configuration = NSWorkspace.OpenConfiguration()
        if inBackground {
            configuration.activates = false
            configuration.hides = true
            configuration.addsToRecentItems = false
        }
        workspace.openApplication(at: url, configuration: configuration) { _, error in
            if let error { NSLog("rMirror: could not open the reMarkable app: \(error.localizedDescription)") }
        }
        return true
    }
    // Lives as long as the app (owned by the store), so the observers are never removed.
}
