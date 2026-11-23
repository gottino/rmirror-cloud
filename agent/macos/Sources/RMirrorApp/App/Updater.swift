import AppKit
import RMirrorKit

/// Update checks. This placeholder uses the core's version check and offers the download page.
/// The Sparkle integration replaces the body of `checkForUpdates` when it is configured.
@MainActor
final class Updater {
    static let shared = Updater()

    func checkForUpdates(store: AppStore, showWindow: @escaping () -> Void) {
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
