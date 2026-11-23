import Foundation

/// Words for the onboarding screens (starting, sign-in, reMarkable app, permission, first sync).
/// Anything shared with other screens (progress, results, allowance, problems) lives in
/// `SharedCopy`; this file only adds what those screens need on top.
///
/// Plain language from the user's side: sentence case, no exclamation marks, no jargon.
public enum OnboardingCopy {
    // MARK: Common actions

    public static let tryAgain = "Try again"
    public static let quit = "Quit rMirror"
    public static let cancel = "Cancel"
    public static let done = "Done"
    /// Said while rMirror waits for something outside the app to change.
    public static let checksByItself = "rMirror checks again by itself."

    // MARK: Starting

    public static let startingTitle = "Starting rMirror…"
    public static let startingMessage = "This only takes a moment."

    // MARK: Could not start

    public static let otherCopyTitle = "Another copy of rMirror is already running"
    public static let otherCopyMessage = "Only one copy can run at a time. Quit the other one, then try again."
    public static let otherCopyHowTo = "It is usually the older rMirror in the menu bar. Click its icon there and choose Quit."

    public static let cannotStartTitle = "rMirror could not start"
    /// Shown when part of the app is missing, so reinstalling is the real fix.
    public static let cannotStartMissingPart = "Part of rMirror seems to be missing. Download rMirror again and replace the copy in your Applications folder."
    public static let cannotStartMessage = "Something stopped rMirror from starting. Try again. If it keeps happening, restart your Mac and open rMirror again."

    // MARK: Sign in

    public static let signInTitle = "Sign in to rMirror"
    public static let signInIntro = "rMirror copies the notebooks from your reMarkable app to rMirror Cloud, where your handwriting is turned into text."
    public static let signInRenewTitle = "Your sign-in needs renewing"
    public static let signInRenewMessage = "rMirror has paused syncing until you sign in again. Your notebooks are safe, and syncing carries on where it stopped."
    public static let signInButton = "Sign in"
    public static let signInHint = "Signing in opens in your web browser."

    public static let connectingTitle = "Connecting your Mac…"
    public static let connectingMessage = "Finish signing in in your browser, then come back here."
    public static let openSignInAgain = "Open the sign-in page again"

    // MARK: reMarkable app missing

    public static let remarkableMissingTitle = "rMirror needs the reMarkable desktop app"
    public static let remarkableMissingMessage = "rMirror reads your notebooks from the reMarkable app on this Mac. It is not installed yet, or it has not synced any notebooks."
    public static let remarkableMissingSteps = [
        "Install the reMarkable desktop app.",
        "Open it and sign in with your reMarkable account.",
        "Leave it open until your notebooks have finished syncing.",
    ]
    public static let getRemarkableApp = "Get the reMarkable app"
    public static let waitingForRemarkable = "Waiting for the reMarkable app. rMirror notices by itself when it is ready."

    // MARK: Permission

    public static let permissionTitle = "Allow rMirror to read your notebooks"
    public static let permissionWhy = "Your notebooks are stored in the reMarkable app's own folder, which macOS protects. rMirror only reads them and never changes them."
    public static let permissionStepOpen = "Open the Full Disk Access list in System Settings."
    public static let permissionStepTurnOn = "Turn on rMirror in the list. If rMirror is not there, click the + button and choose rMirror from your Applications folder."
    public static let permissionStepReopen = "macOS asks to quit and reopen rMirror. Agree, or reopen it here."
    public static let permissionStepReopenManually = "macOS asks to quit and reopen rMirror. Agree, or quit rMirror and open it again."
    public static let openSystemSettings = "Open System Settings"
    public static let reopen = "Reopen rMirror"

    // MARK: First sync: suggestion

    /// "Start with your 3 most recent notebooks"
    public static func suggestionTitle(count: Int) -> String {
        count == 1 ? "Start with your most recent notebook" : "Start with your \(count) most recent notebooks"
    }

    public static let suggestionMessage = "rMirror uploads them and turns your handwriting into text. You can add more notebooks later."
    public static let chooseTitle = "Choose notebooks to sync"
    public static let chooseMessage = "Tick the notebooks you want in rMirror. You can change this later."
    public static let chooseDifferent = "Choose different notebooks"
    public static let backToSuggestion = "Back to the suggested notebooks"
    public static let searchPrompt = "Search notebooks"

    /// "No notebooks match “Book”."
    public static func noMatches(_ query: String) -> String { "No notebooks match “\(query)”." }

    /// "Sync 3 notebooks (23 pages)"
    public static func syncButton(notebooks: Int, pages: Int) -> String {
        "Sync \(SharedCopy.notebooks(notebooks)) (\(SharedCopy.pages(pages)))"
    }

    public static let nothingTicked = "Tick at least one notebook to sync."

    /// "That's more than the 12 pages you have left this month. Untick a notebook."
    public static func overAllowance(remaining: Int) -> String {
        "That's more than the \(SharedCopy.pages(remaining)) you have left this month. Untick a notebook."
    }

    /// Accessibility label for a notebook checkbox row: "Meeting Notes, in Work, 12 pages".
    public static func notebookRow(name: String, folder: String?, pages: Int) -> String {
        if let folder, !folder.isEmpty { return "\(name), in \(folder), \(SharedCopy.pages(pages))" }
        return "\(name), \(SharedCopy.pages(pages))"
    }

    // MARK: First sync: other situations

    public static let loadingSuggestion = "Finding your recent notebooks…"
    public static let preparing = "Getting things ready…"

    public static let noNotebooksTitle = "Your reMarkable app has no notebooks yet"
    public static let noNotebooksMessage = "Write something on your reMarkable and let the desktop app sync it. rMirror notices new notebooks by itself."
    public static let waitingForNotebooks = "Waiting for your first notebook…"

    public static let noPagesLeftTitle = "You have no pages left this month"
    public static let noPagesLeftMessage = "Your notebooks can still upload now. They are turned into text when your pages reset."
    public static let noPagesLeftNothingToUpload = "When your pages reset, rMirror can turn your notebooks into text again. This screen moves on by itself."

    /// "Upload 3 notebooks now"
    public static func uploadNowButton(notebooks: Int) -> String {
        "Upload \(SharedCopy.notebooks(notebooks)) now"
    }

    // MARK: First sync: progress

    public static let progressTitle = "Syncing your notebooks"
    public static let progressReassurance = "You can close this window. Syncing carries on from the menu bar, and your notebooks also appear on the rMirror website."

    // MARK: First sync: result

    public static let openOnWeb = "Open my notebooks on the web"
    public static let whatHappensNext = "From now on, new and changed pages sync automatically."

    // MARK: All strings

    /// Every string above, with representative arguments for the functions. Used by tests to
    /// check the wording stays free of technical terms.
    public static var allStrings: [String] {
        [
            tryAgain, quit, cancel, done, checksByItself,
            startingTitle, startingMessage,
            otherCopyTitle, otherCopyMessage, otherCopyHowTo,
            cannotStartTitle, cannotStartMissingPart, cannotStartMessage,
            signInTitle, signInIntro, signInRenewTitle, signInRenewMessage, signInButton, signInHint,
            connectingTitle, connectingMessage, openSignInAgain,
            remarkableMissingTitle, remarkableMissingMessage, getRemarkableApp, waitingForRemarkable,
            permissionTitle, permissionWhy, permissionStepOpen, permissionStepTurnOn,
            permissionStepReopen, permissionStepReopenManually, openSystemSettings, reopen,
            suggestionTitle(count: 1), suggestionTitle(count: 3), suggestionMessage,
            chooseTitle, chooseMessage, chooseDifferent, backToSuggestion, searchPrompt,
            noMatches("Book"),
            syncButton(notebooks: 1, pages: 1), syncButton(notebooks: 3, pages: 23),
            nothingTicked, overAllowance(remaining: 1), overAllowance(remaining: 12),
            notebookRow(name: "Meeting Notes", folder: "Work", pages: 12),
            notebookRow(name: "Book Club", folder: nil, pages: 1),
            loadingSuggestion, preparing,
            noNotebooksTitle, noNotebooksMessage, waitingForNotebooks,
            noPagesLeftTitle, noPagesLeftMessage, noPagesLeftNothingToUpload,
            uploadNowButton(notebooks: 1), uploadNowButton(notebooks: 3),
            progressTitle, progressReassurance,
            openOnWeb, whatHappensNext,
        ] + remarkableMissingSteps
    }
}
