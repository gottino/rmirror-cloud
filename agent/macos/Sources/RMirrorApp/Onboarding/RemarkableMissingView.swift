import RMirrorKit
import SwiftUI

/// The reMarkable desktop app is not installed or has never synced. The store keeps polling,
/// so this screen moves on by itself once the app's folder appears.
struct RemarkableMissingView: View {
    static let downloadURL = "https://my.remarkable.com/desktop"

    var body: some View {
        OnboardingScaffold(
            symbol: "arrow.down.app",
            title: OnboardingCopy.remarkableMissingTitle,
            message: OnboardingCopy.remarkableMissingMessage
        ) {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                ForEach(Array(OnboardingCopy.remarkableMissingSteps.enumerated()), id: \.offset) { index, step in
                    OnboardingStep(number: index + 1, text: step)
                }
            }
            .rmCard()
        } actions: {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                Button(OnboardingCopy.getRemarkableApp) { OnboardingSystem.open(Self.downloadURL) }
                    .buttonStyle(.rmPrimary)
                    .keyboardShortcut(.defaultAction)
                OnboardingWaitingLine(text: OnboardingCopy.waitingForRemarkable)
            }
        }
    }
}
