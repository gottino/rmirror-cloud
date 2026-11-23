import RMirrorKit
import SwiftUI

/// Sign-in happens in the browser. This screen starts it and waits for it to finish.
struct SignInView: View {
    @EnvironmentObject private var store: AppStore
    let reason: Stage.SignInReason

    var body: some View {
        if store.isWaitingForSignIn {
            waiting
        } else {
            start
        }
    }

    private var start: some View {
        OnboardingScaffold(
            title: reason == .expired ? OnboardingCopy.signInRenewTitle : OnboardingCopy.signInTitle,
            message: reason == .expired ? OnboardingCopy.signInRenewMessage : OnboardingCopy.signInIntro
        ) {
            OnboardingProblemLine(problem: store.problem)
        } actions: {
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                Button(OnboardingCopy.signInButton) { Task { await store.beginSignIn() } }
                    .buttonStyle(.rmPrimary)
                    .keyboardShortcut(.defaultAction)
                Text(OnboardingCopy.signInHint)
                    .font(Theme.Font.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
    }

    private var waiting: some View {
        OnboardingScaffold(title: OnboardingCopy.connectingTitle) {
            OnboardingWaitingLine(text: OnboardingCopy.connectingMessage)
        } actions: {
            HStack(spacing: Theme.Space.l) {
                Button(OnboardingCopy.openSignInAgain) { Task { await store.beginSignIn() } }
                    .buttonStyle(.rmLink)
                Button(OnboardingCopy.cancel) { store.cancelSignIn() }
                    .buttonStyle(.rmLink)
                    .keyboardShortcut(.cancelAction)
            }
        }
    }
}
