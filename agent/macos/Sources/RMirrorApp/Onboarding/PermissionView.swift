import RMirrorKit
import SwiftUI

/// macOS blocks rMirror from reading the reMarkable app's folder (Full Disk Access).
/// The store keeps polling, so if access appears without a relaunch the screen moves on.
struct PermissionView: View {
    static let settingsURL = "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles"

    var body: some View {
        OnboardingScaffold(
            symbol: "lock.shield",
            title: OnboardingCopy.permissionTitle,
            message: OnboardingCopy.permissionWhy
        ) {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                OnboardingStep(number: 1, text: OnboardingCopy.permissionStepOpen) {
                    Button(OnboardingCopy.openSystemSettings) { OnboardingSystem.open(Self.settingsURL) }
                        .buttonStyle(.rmPrimary)
                        .keyboardShortcut(.defaultAction)
                }
                OnboardingStep(number: 2, text: OnboardingCopy.permissionStepTurnOn)
                if OnboardingSystem.canRelaunch {
                    OnboardingStep(number: 3, text: OnboardingCopy.permissionStepReopen) {
                        Button(OnboardingCopy.reopen) { OnboardingSystem.relaunch() }
                            .buttonStyle(.rmSecondary)
                    }
                } else {
                    OnboardingStep(number: 3, text: OnboardingCopy.permissionStepReopenManually)
                }
            }
            .rmCard()
        } actions: {
            OnboardingWaitingLine(text: OnboardingCopy.checksByItself)
        }
    }
}
