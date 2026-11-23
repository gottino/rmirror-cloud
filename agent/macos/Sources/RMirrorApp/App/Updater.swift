import AppKit
import RMirrorKit
import Sparkle

/// Update checks.
///
/// Sparkle is active only when the bundle's Info.plist has both a non-empty `SUFeedURL` and a
/// non-empty `SUPublicEDKey`. Otherwise (including `swift build` runs outside a bundle) nothing from
/// Sparkle is instantiated and the fallback below is used: the core's `version.json` check plus an alert.
/// See `docs/sparkle.md`.
///
/// Background (scheduled) checks follow Sparkle's gentle-reminder guidance for background apps: the
/// app never switches to a regular app, opens a window or activates itself for them. It shows a
/// reminder it controls instead (`updateAvailable`, shown as "Update Available…" in the menu bar
/// item, plus a Dock badge while the Dock icon is visible). Choosing it runs a user-initiated check,
/// which brings the update window forward.
@MainActor
final class Updater: NSObject {
    static let shared = Updater()

    private var controller: SPUStandardUpdaterController?
    private var started = false

    /// True when Sparkle is configured and running.
    var isSparkleActive: Bool { controller != nil }

    /// A background check found an update the user has not looked at yet. Independent of the store.
    private(set) var updateAvailable = false {
        didSet {
            guard updateAvailable != oldValue else { return }
            refreshDockBadge()
            onUpdateAvailableChange?(updateAvailable)
        }
    }

    /// Called whenever `updateAvailable` changes (the menu bar item shows or hides its entry).
    var onUpdateAvailableChange: ((Bool) -> Void)?

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

    /// The Dock badge is a reminder only while the Dock icon is visible (a window is open).
    /// Call when the activation policy may have changed.
    func refreshDockBadge() {
        let showBadge = updateAvailable && NSApp.activationPolicy() == .regular
        NSApp.dockTile.badgeLabel = showBadge ? "1" : ""
    }

    /// A check the user asked for (menu bar item, or the "Update Available…" reminder): this one may
    /// bring rMirror forward.
    func checkForUpdates(store: AppStore, showWindow: @escaping () -> Void) {
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
            let copy = AppCopy.Update.self
            switch result {
            case .checked(let check) where check.hasUpdate && check.latestVersion != nil:
                alert.messageText = copy.availableTitle(check.latestVersion ?? "")
                alert.informativeText = copy.availableBody(current: check.currentVersion)
                alert.addButton(withTitle: copy.download)
                alert.addButton(withTitle: copy.later)
                NSApp.activate(ignoringOtherApps: true)
                if alert.runModal() == .alertFirstButtonReturn, let url = SafeURL.browserURL(from: check.downloadURL) {
                    NSWorkspace.shared.open(url)
                }
            case .checked:
                alert.messageText = copy.upToDate
                alert.addButton(withTitle: copy.ok)
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            case .coreNotRunning, .failed:
                alert.messageText = copy.checkFailedTitle
                alert.informativeText = result == .coreNotRunning ? copy.checkFailedNotRunning : copy.checkFailedOffline
                alert.addButton(withTitle: copy.ok)
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            }
        }
    }
}

// Gentle reminders for background apps (https://sparkle-project.org/documentation/gentle-reminders).
extension Updater: SPUStandardUserDriverDelegate {
    nonisolated var supportsGentleScheduledUpdateReminders: Bool { true }

    /// Scheduled checks: rMirror shows the reminder itself and never pops Sparkle's window over
    /// whatever the user is doing. User-initiated checks are always shown by Sparkle.
    nonisolated func standardUserDriverShouldHandleShowingScheduledUpdate(
        _ update: SUAppcastItem, andInImmediateFocus immediateFocus: Bool
    ) -> Bool {
        false
    }

    nonisolated func standardUserDriverWillHandleShowingUpdate(
        _ handleShowingUpdate: Bool, forUpdate update: SUAppcastItem, state: SPUUserUpdateState
    ) {
        let userInitiated = state.userInitiated
        Task { @MainActor in
            if userInitiated {
                // The user asked: make sure the update window is reachable (Dock icon, Cmd-Tab).
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
            } else {
                // Keep it for when the user next opens rMirror.
                self.updateAvailable = true
            }
        }
    }

    nonisolated func standardUserDriverDidReceiveUserAttention(forUpdate update: SUAppcastItem) {
        Task { @MainActor in self.updateAvailable = false }
    }

    // The window coordinator decides when to return to `.accessory` (when no window of the app is
    // left, Sparkle's included), so the policy is deliberately not changed here.
    nonisolated func standardUserDriverWillFinishUpdateSession() {
        Task { @MainActor in self.updateAvailable = false }
    }
}
