import AppKit
import RMirrorKit
import Sparkle

/// Update checks.
///
/// Sparkle is active only when the bundle's Info.plist has both a non-empty `SUFeedURL` and a
/// non-empty `SUPublicEDKey`. Otherwise (including `swift build` runs outside a bundle) nothing from
/// Sparkle is instantiated and the fallback below is used: the core's `version.json` check plus an alert.
/// See `docs/sparkle.md`.
@MainActor
final class Updater: NSObject {
    static let shared = Updater()

    private var controller: SPUStandardUpdaterController?
    private var presenter: (() -> Void)?
    private var started = false

    /// True when Sparkle is configured and running.
    var isSparkleActive: Bool { controller != nil }

    private override init() {
        super.init()
        start()  // lazy start on first access of `Updater.shared`
    }

    private static func plistString(_ key: String) -> String? {
        guard let value = Bundle.main.infoDictionary?[key] as? String else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Starts Sparkle when configured. Idempotent. Call once at launch.
    func start() {
        guard !started else { return }
        started = true
        guard Self.plistString("SUFeedURL") != nil, Self.plistString("SUPublicEDKey") != nil else { return }
        controller = SPUStandardUpdaterController(
            startingUpdater: true, updaterDelegate: nil, userDriverDelegate: self)
    }

    /// Closure used to bring the app forward (e.g. show the main window) when Sparkle has an update to show.
    func setPresenter(_ presenter: @escaping () -> Void) {
        self.presenter = presenter
    }

    func checkForUpdates(store: AppStore, showWindow: @escaping () -> Void) {
        if presenter == nil { presenter = showWindow }
        if let controller {
            showWindow()
            NSApp.activate(ignoringOtherApps: true)
            controller.checkForUpdates(nil)
            return
        }
        fallbackCheck(store: store)
    }

    private func fallbackCheck(store: AppStore) {
        Task {
            let result = await store.checkForUpdate()
            let alert = NSAlert()
            if let result, result.hasUpdate, let version = result.latestVersion {
                alert.messageText = "rMirror \(version) is available"
                alert.informativeText = "You have \(result.currentVersion). Download the new version and replace rMirror in your Applications folder."
                alert.addButton(withTitle: "Download")
                alert.addButton(withTitle: "Later")
                NSApp.activate(ignoringOtherApps: true)
                if alert.runModal() == .alertFirstButtonReturn, let link = result.downloadURL, let url = URL(string: link) {
                    NSWorkspace.shared.open(url)
                }
            } else if result != nil {
                alert.messageText = "rMirror is up to date"
                alert.addButton(withTitle: "OK")
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            } else {
                alert.messageText = "Could not check for updates"
                alert.informativeText = "Check your internet connection and try again."
                alert.addButton(withTitle: "OK")
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            }
        }
    }
}

// Gentle reminders for background apps (Sparkle docs: "Gentle reminders").
extension Updater: SPUStandardUserDriverDelegate {
    nonisolated var supportsGentleScheduledUpdateReminders: Bool { true }

    nonisolated func standardUserDriverWillHandleShowingUpdate(
        _ handleShowingUpdate: Bool, forUpdate update: SUAppcastItem, state: SPUUserUpdateState
    ) {
        Task { @MainActor in
            // Show the Dock icon so the update window is reachable via Cmd-Tab and not lost behind others.
            NSApp.setActivationPolicy(.regular)
            self.presenter?()
            NSApp.activate(ignoringOtherApps: true)
            if !state.userInitiated { NSApp.dockTile.badgeLabel = "1" }
        }
    }

    nonisolated func standardUserDriverDidReceiveUserAttention(forUpdate update: SUAppcastItem) {
        Task { @MainActor in NSApp.dockTile.badgeLabel = "" }
    }

    // The app's own window manager decides when to return to `.accessory` (when its last window closes),
    // so the policy is deliberately not changed here.
    nonisolated func standardUserDriverWillFinishUpdateSession() {
        Task { @MainActor in NSApp.dockTile.badgeLabel = "" }
    }
}
