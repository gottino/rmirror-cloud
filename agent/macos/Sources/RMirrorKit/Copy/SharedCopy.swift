import Foundation

/// Words shared by more than one screen: sync progress and results, the one-line status, the
/// page allowance, and action problems. Plain language only: nothing here mentions tokens,
/// rate limits, callbacks, queues or logs. Screen-specific wording lives next to it in
/// `OnboardingCopy`, `MainCopy` and `SettingsCopy`.
public enum SharedCopy {
    // MARK: Counting

    public static func pages(_ count: Int) -> String { count == 1 ? "1 page" : "\(count) pages" }
    public static func notebooks(_ count: Int) -> String { count == 1 ? "1 notebook" : "\(count) notebooks" }

    // MARK: Sync progress and result

    /// "4 of 23 pages uploaded" (or "4 pages uploaded" when the total is not known).
    public static func progressLine(_ counts: SyncCounts) -> String {
        if let total = counts.pagesTotal, total > 0 {
            return "\(min(counts.uploaded, total)) of \(pages(total)) uploaded"
        }
        return "\(pages(counts.uploaded)) uploaded"
    }

    /// "Notebook 2 of 3"
    public static func notebookProgressLine(_ counts: SyncCounts) -> String? {
        guard counts.notebooksTotal > 0 else { return nil }
        let current = min(counts.notebooksDone + 1, counts.notebooksTotal)
        return "Notebook \(current) of \(counts.notebooksTotal)"
    }

    /// 0...1, or nil when the total is not known yet.
    public static func progressFraction(_ counts: SyncCounts) -> Double? {
        guard let total = counts.pagesTotal, total > 0 else { return nil }
        let handled = counts.uploaded + counts.failed + counts.willRetry
        return min(1, Double(handled) / Double(total))
    }

    public static func resultTitle(_ progress: SyncProgress) -> String {
        switch progress.outcome {
        case .success?: return "Your notebooks are in rMirror"
        case .partial?: return progress.counts.uploaded > 0 ? "Most of your pages are in rMirror" : "Some pages could not be uploaded"
        case .stoppedQuota?: return "You've used this month's pages"
        case .stoppedSignIn?: return "Please sign in again"
        case .failed?: return "The sync could not finish"
        default: return "Sync finished"
        }
    }

    /// One short line per thing the user should know, most important first.
    public static func resultDetails(_ progress: SyncProgress) -> [String] {
        let counts = progress.counts
        var lines: [String] = []
        if counts.uploaded > 0 { lines.append("\(pages(counts.uploaded)) uploaded.") }
        if counts.willRetry > 0 {
            lines.append("\(pages(counts.willRetry)) will upload shortly. You don't need to do anything.")
        }
        if counts.failed > 0 {
            lines.append("\(pages(counts.failed)) could not be uploaded. Try again.")
        }
        if counts.leftOutByPageLimit > 0 {
            lines.append("\(pages(counts.leftOutByPageLimit)) left out because of your page limit. Older pages are skipped first.")
        }
        switch progress.outcome {
        case .stoppedQuota?:
            lines.append("The rest will be transcribed when your pages reset.")
        case .stoppedSignIn?:
            lines.append("Sign in again and the sync continues where it stopped.")
        case .failed? where counts.uploaded == 0 && counts.failed == 0:
            lines.append("Nothing was uploaded. Check your internet connection and try again.")
        default:
            break
        }
        return lines
    }

    /// Whether the result screen should offer "Try again".
    public static func resultOffersRetry(_ progress: SyncProgress) -> Bool {
        switch progress.outcome {
        case .partial?, .failed?: return true
        default: return false
        }
    }

    // MARK: Page allowance

    /// "196 of 200 pages left this month" / "Unlimited pages"
    public static func allowance(_ quota: QuotaInfo) -> String {
        if quota.isUnlimited { return "Unlimited pages" }
        let remaining = quota.remaining ?? max(0, quota.limit - quota.used)
        return "\(remaining) of \(pages(quota.limit)) left this month"
    }

    /// "Resets 1 December"
    public static func allowanceReset(_ quota: QuotaInfo, calendar: Calendar = .current, locale: Locale = .current) -> String? {
        guard !quota.isUnlimited, let reset = quota.resetAt else { return nil }
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.locale = locale
        formatter.timeZone = calendar.timeZone
        formatter.setLocalizedDateFormatFromTemplate("d MMMM")
        return "Resets \(formatter.string(from: reset))"
    }

    /// "Uses 23 of your 196 remaining pages" for a planned sync.
    public static func allowanceUse(pages planned: Int, remaining: Int?) -> String {
        guard let remaining else { return "Uses \(pages(planned))" }
        return "Uses \(planned) of your \(remaining) remaining \(remaining == 1 ? "page" : "pages") this month"
    }

    // MARK: One-line status (menu bar, window header)

    public static func statusLine(stage: Stage, state: AppState?) -> String {
        switch stage {
        case .starting: return "Starting…"
        case .coreProblem(.portInUse): return "Another copy of rMirror is running"
        case .coreProblem: return "rMirror needs attention"
        case .signIn(.expired): return "Sign in again to keep syncing"
        case .signIn: return "Not signed in"
        case .remarkableMissing: return "reMarkable app not found"
        case .permission: return "Needs permission to read your notebooks"
        case .firstSync: return "Ready for your first sync"
        case .firstSyncProgress, .firstSyncResult, .ready: break
        }
        guard let state else { return "Starting…" }
        if state.sync.state == .running { return "Syncing: \(progressLine(state.sync.counts))" }
        switch state.queue.pausedReason {
        case .quota?: return "Paused: no pages left this month"
        case .signIn?: return "Sign in again to keep syncing"
        case .offline?: return "Waiting for an internet connection"
        case .rateLimited?: return "Catching up…"
        default: break
        }
        if state.queue.pending > 0 { return "Uploading \(pages(state.queue.pending))…" }
        if let last = state.lastUploadAt { return "Up to date · last upload \(relative(last))" }
        return "Up to date"
    }

    /// "5 minutes ago", "yesterday"
    public static func relative(_ date: Date, now: Date = Date(), locale: Locale = .current) -> String {
        // Also covers a clock that is slightly ahead on the other side: never say "in 5 minutes".
        if now.timeIntervalSince(date) < 60 { return "just now" }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = locale
        formatter.unitsStyle = .full
        formatter.dateTimeStyle = .named
        return formatter.localizedString(for: date, relativeTo: now)
    }

    // MARK: Problems

    public static func problem(_ problem: ActionProblem) -> String {
        switch problem {
        case .coreUnreachable: return "rMirror is still starting. Try again in a moment."
        case .notSignedIn: return "Please sign in first."
        case .syncAlreadyRunning: return "A sync is already running."
        case .cloudUnavailable: return "rMirror Cloud did not answer. Check your internet connection and try again."
        case .other: return "That didn't work. Try again."
        }
    }
}
