import RMirrorKit
import SwiftUI

/// The main window's content: exactly one screen, chosen by the store's stage.
struct RootView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        Group {
            switch store.stage {
            case .starting: StartingView()
            case .coreProblem(let failure): CoreProblemView(failure: failure)
            case .signIn(let reason): SignInView(reason: reason)
            case .remarkableMissing: RemarkableMissingView()
            case .permission: PermissionView()
            case .firstSync: FirstSyncView()
            case .firstSyncProgress: FirstSyncProgressView()
            case .firstSyncResult: FirstSyncResultView()
            case .ready: MainView()
            }
        }
        .rmScreen()
        .animation(.easeInOut(duration: 0.2), value: store.stage)
    }
}
