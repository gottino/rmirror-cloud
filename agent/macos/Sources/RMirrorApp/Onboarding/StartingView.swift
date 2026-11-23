import RMirrorKit
import SwiftUI

/// The core is starting (or restarting). Calm, nothing to do.
struct StartingView: View {
    @EnvironmentObject private var store: AppStore
    /// Set once the screen has shown for a while; the supervisor waits up to 90 s for the core.
    @State private var takingLonger = false

    static let slowAfter: UInt64 = 12

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
            Text(takingLonger ? OnboardingCopy.startingSlowMessage : OnboardingCopy.startingMessage)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
        }
        .multilineTextAlignment(.center)
        .padding(Theme.Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
        .task {
            try? await Task.sleep(nanoseconds: Self.slowAfter * 1_000_000_000)
            takingLonger = true
        }
    }
}
