import Foundation

/// Wording for the main window (the notebook list after onboarding). Shared wording such as the status
/// line, the allowance, sync progress and results lives in `SharedCopy`; this file only holds what is
/// specific to this window. Plain language, sentence case, no exclamation marks or em dashes.
public enum MainCopy {
    // MARK: Header

    public static let openOnWeb = "Open on the web"
    public static let settings = "Settings"
    public static let settingsHelp = "Open rMirror settings"
    public static let accountFallback = "Your rMirror account"
    public static func signedInAs(_ email: String) -> String { "Signed in as \(email)" }

    // MARK: Allowance

    public static let allowanceExhaustedTitle = "You've used this month's pages"
    public static let allowanceExhaustedBody = "New pages still upload. They are transcribed after your pages reset."
    public static func allowanceUsedAccessibility(used: Int, limit: Int) -> String {
        "\(used) of \(SharedCopy.pages(limit)) used"
    }

    // MARK: Sync strips

    public static let syncingTitle = "Syncing your notebooks"
    public static let dismiss = "Dismiss"
    public static let tryAgain = "Try again"
    public static let pausedTitle = "Uploads are paused"
    public static let pausedBody = "New pages are waiting to upload. Try again to continue."

    // MARK: Notebook list

    public static let listTitle = "Notebooks to sync"
    public static let listIntro = "Ticked notebooks stay in sync. New pages upload on their own."
    public static let searchPlaceholder = "Search notebooks"
    public static let clearSearch = "Clear search"
    public static let selectAll = "Select all"
    public static let selectNone = "Select none"
    public static let selectAllMatching = "Select all shown"
    public static let selectNoneMatching = "Select none shown"
    /// Heading for notebooks that are not in a folder.
    public static let topLevelGroup = "Notebooks"

    public static func groupAccessibility(folder: String, count: Int) -> String {
        "\(folder), \(SharedCopy.notebooks(count))"
    }

    public static func syncIndicator(_ indicator: SyncIndicator) -> String {
        switch indicator {
        case .empty: return "No pages yet"
        case .notSynced: return "Not synced yet"
        case .partly(let synced, let total): return "\(synced) of \(SharedCopy.pages(total)) synced"
        case .complete(let total): return "\(total) of \(SharedCopy.pages(total)) synced"
        }
    }

    public static let selected = "selected"
    public static let notSelected = "not selected"

    /// VoiceOver label for a row: "Meeting Notes, 12 pages, selected".
    public static func rowAccessibilityLabel(name: String, pages: Int, selected: Bool) -> String {
        "\(name), \(SharedCopy.pages(pages)), \(selected ? Self.selected : notSelected)"
    }

    /// VoiceOver value for a row: where it is and how much has synced.
    public static func rowAccessibilityValue(folder: String?, indicator: String) -> String {
        guard let folder else { return indicator }
        return "In \(folder). \(indicator)"
    }

    public static let rowAccessibilityHint = "Ticks or unticks the notebook"

    // MARK: Empty and loading states

    public static let loading = "Looking for your notebooks…"
    public static let emptyTitle = "No notebooks yet"
    public static let emptyBody = "Notebooks appear here once the reMarkable app on this Mac has them. Open the reMarkable app and let it finish syncing."
    public static func noMatches(_ query: String) -> String { "No notebooks match \u{201C}\(query)\u{201D}" }
    public static let noMatchesBody = "Check the spelling, or search for a folder name."

    // MARK: Pending change

    /// "2 notebooks added · 31 new pages", "1 notebook removed", "1 notebook added · 1 removed · 4 new pages"
    public static func changeSummary(added: Int, removed: Int, newPages: Int) -> String {
        var parts: [String] = []
        if added > 0 { parts.append("\(SharedCopy.notebooks(added)) added") }
        if removed > 0 { parts.append(added > 0 ? "\(removed) removed" : "\(SharedCopy.notebooks(removed)) removed") }
        if added > 0 && newPages > 0 { parts.append("\(newPages) new \(newPages == 1 ? "page" : "pages")") }
        return parts.joined(separator: " · ")
    }

    /// Shown, without blocking, when the new pages are more than the pages left this month.
    public static func overAllowance(remaining: Int) -> String {
        "That's more than the \(SharedCopy.pages(remaining)) you have left this month. The rest will be transcribed after your pages reset."
    }

    public static let removalNote = "Unticked notebooks stop syncing. Pages already in rMirror stay there."
    public static let cancel = "Cancel"
    public static let saveAndSync = "Save and sync"
    public static let save = "Save"
    public static let saving = "Saving…"
    public static let waitForSync = "You can sync these once the current sync finishes."

    // MARK: Removed on the web

    public static let deletedTitle = "Removed on the web"
    public static let deletedBody = "You deleted these notebooks on the rMirror website. Sync one again to bring it back, or keep it removed and rMirror leaves it alone."
    public static let syncAgain = "Sync again"
    public static let keepRemoved = "Keep removed"
    public static func deletedWhen(_ relative: String) -> String { "Removed \(relative)" }

    // MARK: Checks

    /// Every string above, with representative arguments, for wording checks.
    public static var allStrings: [String] {
        [
            openOnWeb, settings, settingsHelp, accountFallback, signedInAs("sample@example.com"),
            allowanceExhaustedTitle, allowanceExhaustedBody, allowanceUsedAccessibility(used: 24, limit: 200),
            syncingTitle, dismiss, tryAgain, pausedTitle, pausedBody,
            listTitle, listIntro, searchPlaceholder, clearSearch, selectAll, selectNone,
            selectAllMatching, selectNoneMatching, topLevelGroup,
            groupAccessibility(folder: "Work", count: 4),
            syncIndicator(.empty), syncIndicator(.notSynced(total: 12)),
            syncIndicator(.partly(synced: 4, total: 12)), syncIndicator(.complete(total: 12)),
            selected, notSelected,
            rowAccessibilityLabel(name: "Meeting Notes", pages: 12, selected: true),
            rowAccessibilityLabel(name: "Quick Notes", pages: 1, selected: false),
            rowAccessibilityValue(folder: "Work / 2026", indicator: syncIndicator(.complete(total: 12))),
            rowAccessibilityHint,
            loading, emptyTitle, emptyBody, noMatches("garden"), noMatchesBody,
            changeSummary(added: 2, removed: 0, newPages: 31), changeSummary(added: 0, removed: 1, newPages: 0),
            changeSummary(added: 1, removed: 2, newPages: 1),
            overAllowance(remaining: 12), overAllowance(remaining: 1),
            removalNote, cancel, saveAndSync, save, saving, waitForSync,
            deletedTitle, deletedBody, syncAgain, keepRemoved, deletedWhen("yesterday"),
        ]
    }
}
