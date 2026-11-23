import AppKit
import RMirrorKit
import SwiftUI

/// rMirror's background part cannot run. Never shows exit codes or paths.
struct CoreProblemView: View {
    @EnvironmentObject private var store: AppStore
    let failure: CoreFailure

    var body: some View {
        OnboardingScaffold(
            symbol: "exclamationmark.triangle",
            symbolTint: Theme.warning,
            title: title,
            message: message
        ) {
            if failure == .portInUse {
                Text(OnboardingCopy.otherCopyHowTo)
                    .font(Theme.Font.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } actions: {
            HStack(spacing: Theme.Space.m) {
                Button(OnboardingCopy.tryAgain) { store.restartCore() }
                    .buttonStyle(.rmPrimary)
                    .keyboardShortcut(.defaultAction)
                if failure != .portInUse {
                    Button(OnboardingCopy.quit) { NSApp.terminate(nil) }
                        .buttonStyle(.rmLink)
                }
            }
        }
    }

    private var title: String {
        failure == .portInUse ? OnboardingCopy.otherCopyTitle : OnboardingCopy.cannotStartTitle
    }

    private var message: String {
        switch failure {
        case .portInUse: return OnboardingCopy.otherCopyMessage
        case .cannotLaunch: return OnboardingCopy.cannotStartMissingPart
        case .readyTimeout, .crashLoop: return OnboardingCopy.cannotStartMessage
        }
    }
}
