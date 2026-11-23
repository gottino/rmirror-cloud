import RMirrorKit
import SwiftUI

/// The core is starting (or restarting). Calm, nothing to do.
struct StartingView: View {
    @EnvironmentObject private var store: AppStore

    /// The core is up and is checking the saved sign-in with rMirror Cloud.
    private var isCheckingSignIn: Bool { store.state?.auth.state == .checking }

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            ProgressView()
                .controlSize(.regular)
                .accessibilityHidden(true)
            Text(isCheckingSignIn ? OnboardingCopy.checkingSignIn : OnboardingCopy.startingTitle)
                .font(Theme.Font.heading)
                .foregroundStyle(Theme.text)
            Text(OnboardingCopy.startingMessage)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
        }
        .multilineTextAlignment(.center)
        .padding(Theme.Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}
