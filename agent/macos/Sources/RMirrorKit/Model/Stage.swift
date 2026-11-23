import Foundation

/// Which screen the main window shows. Derived from the core's status and state; views never
/// decide this themselves.
public enum Stage: Equatable, Sendable {
    /// The core is starting (or restarting after a crash).
    case starting
    /// The core cannot run. The associated value says why.
    case coreProblem(CoreFailure)
    case signIn(reason: SignInReason)
    /// The reMarkable desktop app's folder does not exist.
    case remarkableMissing
    /// The folder exists but macOS will not let rMirror read it.
    case permission
    /// Signed in, folder readable, nothing synced yet: the guided first sync.
    case firstSync
    /// The guided first sync is running.
    case firstSyncProgress
    /// The guided first sync finished; shows the result until the user moves on.
    case firstSyncResult
    /// Normal use: the main window.
    case ready

    public enum SignInReason: Equatable, Sendable {
        case signedOut
        /// The saved sign-in stopped working and has to be renewed.
        case expired
    }

    /// - Parameter guidedSyncActive: the user started the guided first sync in this session
    ///   and has not dismissed its result yet.
    public static func derive(core: CoreStatus, state: AppState?, guidedSyncActive: Bool) -> Stage {
        switch core {
        case .failed(let failure): return .coreProblem(failure)
        case .stopped, .starting, .restarting: return .starting
        case .running: break
        }
        guard let state else { return .starting }

        if state.auth.signInRequired { return .signIn(reason: .expired) }
        switch state.auth.state {
        case .checking:
            // A stored sign-in is being checked: do not flash the sign-in screen meanwhile.
            return .starting
        case .offline:
            // Signed in before, cloud unreachable right now: carry on; the status line says so.
            break
        default:
            if !state.auth.signedIn { return .signIn(reason: .signedOut) }
        }

        switch state.folder.state {
        case .missing: return .remarkableMissing
        case .unreadable: return .permission
        default: break
        }

        if guidedSyncActive {
            switch state.sync.state {
            case .running: return .firstSyncProgress
            case .done: return .firstSyncResult
            default: break
            }
        }
        if !state.firstSync.completed {
            // A first sync started some other way (or before a relaunch) is still worth showing.
            return state.sync.state == .running ? .firstSyncProgress : .firstSync
        }
        return .ready
    }
}
