import Foundation
import RMirrorKit

/// Small decisions about what the window shows, kept apart from the layout.
enum MainStatus {
    /// Colour of the header pill. The pill always carries words, so the tone is never the only signal.
    static func tone(stage: Stage, state: AppState?) -> StatusPill.Tone {
        if case .signIn = stage { return .problem }
        guard let state else { return .neutral }
        if state.sync.state == .running { return .good }
        switch state.queue.pausedReason {
        case .signIn?: return .problem
        case .quota?, .offline?: return .attention
        case .rateLimited?: return .neutral
        case .unknown?: return .attention
        case nil: return .good
        }
    }

    /// Whether to offer "Try again" for paused uploads: only when retrying can actually help.
    ///
    /// - offline / rate limited: the core resumes on its own; the status line says what is happening.
    /// - sign-in: the window switches to the sign-in screen.
    /// - allowance used up: retrying cannot help, so no button. But if pages are available again
    ///   (the month reset or the plan changed) while uploads are still paused, retrying does help.
    /// - any other reason the app does not know: retrying is the only thing the user can do.
    static func offersResume(_ state: AppState) -> Bool {
        guard state.sync.state != .running, let reason = state.queue.pausedReason else { return false }
        switch reason {
        case .offline, .rateLimited, .signIn: return false
        case .quota: return state.quota.map { !$0.isExhausted } ?? false
        case .unknown: return true
        }
    }

    /// Whether a finished sync's result is worth a strip in the main window.
    static func showsResult(_ progress: SyncProgress) -> Bool {
        progress.outcome == .partial || progress.outcome == .failed || progress.outcome == .stoppedQuota
    }

    /// "https://rmirror.io" -> "https://rmirror.io/dashboard"; nil unless `SafeURL` allows it.
    static func dashboardURL(_ state: AppState?) -> URL? {
        SafeURL.dashboardURL(base: state?.environment.dashboardURL)
    }
}
