import Foundation

/// Words for the app's frame: window titles, the menu bar item, the main menu and the update alerts.
/// Menu titles follow the macOS conventions (title case, ellipsis for commands that open a window).
public enum AppCopy {
    public static let appName = "rMirror"
    public static let mainWindowTitle = "rMirror"
    public static let settingsWindowTitle = "rMirror Settings"

    /// The menu bar item.
    public enum StatusMenu {
        public static let open = "Open rMirror"
        public static let settings = "Settings…"
        public static let checkForUpdates = "Check for Updates…"
        /// Shown after a background check found an update; opens the update window.
        public static let updateAvailable = "Update Available…"
        public static let quit = "Quit rMirror"
        public static func tooltip(_ status: String) -> String { "rMirror: \(status)" }
    }

    /// The main menu (shown while a window is open; its shortcuts work whenever rMirror is active).
    public enum MainMenu {
        public static let about = "About rMirror"
        public static let settings = "Settings…"
        public static let hide = "Hide rMirror"
        public static let hideOthers = "Hide Others"
        public static let showAll = "Show All"
        public static let quit = "Quit rMirror"
        public static let edit = "Edit"
        public static let undo = "Undo"
        public static let redo = "Redo"
        public static let cut = "Cut"
        public static let copy = "Copy"
        public static let paste = "Paste"
        public static let selectAll = "Select All"
        public static let window = "Window"
        public static let minimise = "Minimise"
        public static let close = "Close"
        public static let bringAllToFront = "Bring All to Front"
    }

    /// The update alerts used when automatic updates are not set up in this build.
    public enum Update {
        public static func availableTitle(_ version: String) -> String { "rMirror \(version) is available" }
        public static func availableBody(current: String) -> String {
            "You have \(current). Download the new version and replace rMirror in your Applications folder."
        }
        public static let download = "Download"
        public static let later = "Later"
        public static let upToDate = "rMirror is up to date"
        public static let ok = "OK"
        public static let checkFailedTitle = "Could not check for updates"
        /// The check reached the cloud side and failed.
        public static let checkFailedOffline = "Check your internet connection and try again."
        /// rMirror's own sync part is not running, so the internet is not to blame.
        public static let checkFailedNotRunning = "rMirror is not ready yet. Try again in a moment, or quit and reopen rMirror."
    }

    /// Every string above, with representative arguments, for wording checks.
    public static var allStrings: [String] {
        [
            appName, mainWindowTitle, settingsWindowTitle,
            StatusMenu.open, StatusMenu.settings, StatusMenu.checkForUpdates, StatusMenu.updateAvailable,
            StatusMenu.quit, StatusMenu.tooltip("Up to date"),
            MainMenu.about, MainMenu.settings, MainMenu.hide, MainMenu.hideOthers, MainMenu.showAll, MainMenu.quit,
            MainMenu.edit, MainMenu.undo, MainMenu.redo, MainMenu.cut, MainMenu.copy, MainMenu.paste,
            MainMenu.selectAll, MainMenu.window, MainMenu.minimise, MainMenu.close, MainMenu.bringAllToFront,
            Update.availableTitle("2.1.0"), Update.availableBody(current: "2.0.0"), Update.download, Update.later,
            Update.upToDate, Update.ok, Update.checkFailedTitle, Update.checkFailedOffline, Update.checkFailedNotRunning,
        ]
    }
}
