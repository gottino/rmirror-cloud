import Foundation

/// Every string in the settings window. Plain, calm, sentence case.
public enum SettingsCopy {
    public static let windowTitle = "Settings"
    public static let loading = "Loading settings"

    // General
    public static let generalHeading = "General"
    public static let openAtLogin = "Open rMirror when I log in"
    public static let loginItemOff = "This was turned off in System Settings. You can turn it back on there."
    public static let openLoginItems = "Open Login Items settings"
    public static let openRemarkableAtStart = "Open the reMarkable app when rMirror starts"
    public static let openRemarkableAtStartExplanation = "It opens hidden in the background, so new pages from your tablet keep arriving."

    // Account
    public static let accountHeading = "Account"
    public static let notSignedIn = "Not signed in"
    public static let signedInAs = "Signed in as"
    public static let signOut = "Sign out"
    public static let signOutConfirmTitle = "Sign out of rMirror?"
    public static let signOutConfirmBody = "Syncing stops until you sign in again. Nothing you already uploaded is removed."
    public static let signOutConfirmAction = "Sign out"
    public static let cancel = "Cancel"

    // Syncing
    public static let syncingHeading = "Syncing"
    public static let moreOptions = "More options"
    public static let limitPages = "Limit pages per notebook"
    public static let limitPagesExplanation = "Only the most recent pages of each notebook are uploaded. Useful for very long notebooks."
    public static let pageLimitField = "Number of pages"
    public static let pageLimitInvalid = "Enter a number from 1 to 9999."
    public static let save = "Save"
    public static let folderLabel = "reMarkable folder"
    public static let folderNotSet = "Not set"
    public static let changeFolder = "Change…"
    public static let chooseFolderPrompt = "Choose"
    public static let chooseFolderMessage = "Choose the folder where the reMarkable desktop app keeps your notebooks."

    // Footer
    public static func version(_ version: String) -> String { "rMirror \(version)" }

    public static let pageLimitRange = 1...9999

    /// Strings for the collapsed "Developer options" section. These may name the API.
    public enum Developer {
        public static let heading = "Developer options"
        public static let note = "For self-hosted servers and testing. Most people never need this."
        public static let server = "Server"
        public static let production = "rMirror Cloud (production)"
        public static let staging = "Staging"
        public static let custom = "Custom"
        public static let urlLabel = "API URL"
        public static let urlPlaceholder = "https://example.com/api/v1"
        public static let urlInvalid = "Enter a web address that starts with https://. Plain http:// works only for a server on this Mac (localhost)."
        public static let apply = "Apply"
        public static let needsSignIn = "Sign in again to use this server."

        public static var allStrings: [String] {
            [heading, note, server, production, staging, custom, urlLabel, urlPlaceholder, urlInvalid, apply, needsSignIn]
        }
    }

    /// Strings outside Developer options.
    public static var generalStrings: [String] {
        [
            windowTitle, loading, generalHeading, openAtLogin, loginItemOff, openLoginItems,
            openRemarkableAtStart, openRemarkableAtStartExplanation,
            accountHeading, notSignedIn, signedInAs, signOut, signOutConfirmTitle, signOutConfirmBody,
            signOutConfirmAction, cancel, syncingHeading, moreOptions, limitPages, limitPagesExplanation,
            pageLimitField, pageLimitInvalid, save, folderLabel, folderNotSet, changeFolder,
            chooseFolderPrompt, chooseFolderMessage, version("2.0"),
        ]
    }

    public static var allStrings: [String] { generalStrings + Developer.allStrings }

    /// A custom server must be https, or plain http only to this Mac (`SafeURL`); the core enforces the same.
    public static func isValidServerURL(_ text: String) -> Bool {
        SafeURL.isAllowedServerURL(text)
    }
}
