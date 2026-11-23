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
        case .partial?: return progress.counts.uploaded > 0 ? "Some of your pages are in rMirror" : "Some pages could not be uploaded"
        case .stoppedQuota?: return "You've used this month's pages"
        case .stoppedSignIn?: return "Please sign in again"
        case .failed?: return "The sync could not finish"
        default: return "Sync finished"
        }
    }

    /// One short line per thing the user should know, most important first.
    /// - Parameter quota: the allowance, for the reset date after a sync stopped because the pages ran out.
    public static func resultDetails(_ progress: SyncProgress, quota: QuotaInfo? = nil) -> [String] {
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
            // The core does not upload the rest by itself: say so, and when to sync again.
            if let day = quota.flatMap({ resetDay($0) }) {
                lines.append("The rest was not uploaded. Sync again after your pages reset on \(day).")
            } else {
                lines.append("The rest was not uploaded. Sync again after your pages reset.")
            }
        case .stoppedSignIn?:
            lines.append("Sign in again and the sync continues where it stopped.")
        case .failed? where counts.uploaded == 0 && counts.failed == 0:
            lines.append("Nothing was uploaded. Check your internet connection and try again.")
        default:
            break
        }
        return lines
    }

    /// Whether the result screen should offer "Try again". After a sync stopped because the pages ran
    /// out, only once pages are available again (the month reset or the plan changed).
    public static func resultOffersRetry(_ progress: SyncProgress, quota: QuotaInfo? = nil) -> Bool {
        switch progress.outcome {
        case .partial?, .failed?: return true
        case .stoppedQuota?: return quota.map { !$0.isExhausted } ?? false
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

    /// The whole interface is English, so dates and relative times are always formatted in British
    /// English ("1 December", "2 days ago"), whatever the system locale.
    public static let locale = Locale(identifier: "en_GB")

    /// "Resets 1 December"
    /// - Parameter calendar: supplies the time zone only; its locale is ignored.
    public static func allowanceReset(_ quota: QuotaInfo, calendar: Calendar = .current) -> String? {
        resetDay(quota, calendar: calendar).map { "Resets \($0)" }
    }

    /// "1 December": the day the pages reset, or nil when unlimited or unknown.
    public static func resetDay(_ quota: QuotaInfo, calendar: Calendar = .current) -> String? {
        guard !quota.isUnlimited, let reset = quota.resetAt else { return nil }
        var gregorian = Calendar(identifier: .gregorian)
        gregorian.locale = locale
        gregorian.timeZone = calendar.timeZone
        let formatter = DateFormatter()
        formatter.calendar = gregorian
        formatter.locale = locale
        formatter.timeZone = calendar.timeZone
        formatter.dateFormat = "d MMMM"
        return formatter.string(from: reset)
    }

    /// "Uses 23 of your 196 remaining pages" for a planned sync.
    public static func allowanceUse(pages planned: Int, remaining: Int?) -> String {
        guard let remaining else { return "Uses \(pages(planned))" }
        return "Uses \(planned) of your \(remaining) remaining \(remaining == 1 ? "page" : "pages") this month"
    }

    // MARK: One-line status (menu bar, window header)

    public static func statusLine(stage: Stage, state: AppState?) -> String {
        switch stage {
        case .starting:
            guard let state, Stage.isCatchingUp(state) else { return "Starting…" }
            return state.auth.state == .offline ? "Waiting for an internet connection" : "Checking what's already online…"
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
        if state.auth.state == .offline { return "Waiting for an internet connection" }
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

    /// "5 minutes ago", "yesterday", always in English (see `locale`).
    /// - Parameter calendar: supplies the time zone only; its locale is ignored.
    public static func relative(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        // Also covers a clock that is slightly ahead on the other side: never say "in 5 minutes".
        if now.timeIntervalSince(date) < 60 { return "just now" }
        var gregorian = Calendar(identifier: .gregorian)
        gregorian.locale = locale
        gregorian.timeZone = calendar.timeZone
        let formatter = RelativeDateTimeFormatter()
        formatter.calendar = gregorian
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
