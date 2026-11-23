import RMirrorKit
import SwiftUI

/// The core is starting (or restarting). Calm, nothing to do.
struct StartingView: View {
    var body: some View {
        VStack(spacing: Theme.Space.m) {
            ProgressView()
                .controlSize(.regular)
                .accessibilityHidden(true)
            Text(OnboardingCopy.startingTitle)
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
