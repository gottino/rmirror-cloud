import RMirrorKit
import SwiftUI

extension Notification.Name {
    /// Posted by the main window's gear button. The app delegate opens the settings window.
    static let rmirrorOpenSettings = Notification.Name("io.rmirror.openSettings")
}

/// Account, one-line status and the two quiet ways out of the window (website, settings).
struct MainHeader: View {
    let email: String?
    let status: String
    let tone: StatusPill.Tone
    let webURL: URL?

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.m) {
            VStack(alignment: .leading, spacing: 6) {
                Text(email ?? MainCopy.accountFallback)
                    .font(Theme.Font.heading)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .accessibilityLabel(email.map(MainCopy.signedInAs) ?? MainCopy.accountFallback)
                StatusPill(text: status, tone: tone)
                    .lineLimit(1)
            }
            Spacer(minLength: Theme.Space.m)
            if let webURL {
                Button {
                    OnboardingSystem.openInBrowser(webURL)
                } label: {
                    HStack(spacing: 4) {
                        Text(MainCopy.openOnWeb)
                        Image(systemName: "arrow.up.right").font(.system(size: 11, weight: .semibold))
                            .accessibilityHidden(true)
                    }
                }
                .buttonStyle(.rmLink)
                .help(webURL.absoluteString)
            }
            Button {
                NotificationCenter.default.post(name: .rmirrorOpenSettings, object: nil)
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 15))
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(MainIconButtonStyle())
            .help(MainCopy.settingsHelp)
            .accessibilityLabel(MainCopy.settings)
        }
    }
}

/// Allowance for the month: a line with a thin bar, or a calm banner once it is used up.
struct MainAllowance: View {
    let quota: QuotaInfo

    var body: some View {
        if quota.isExhausted {
            MainNotice(kind: .attention, systemImage: "pause.circle", title: MainCopy.allowanceExhaustedTitle,
                       lines: [MainCopy.allowanceExhaustedBody, SharedCopy.allowanceReset(quota)].compactMap { $0 })
        } else {
            HStack(spacing: Theme.Space.s) {
                Text(SharedCopy.allowance(quota))
                    .font(Theme.Font.body)
                    .monospacedDigit()
                if let reset = SharedCopy.allowanceReset(quota) {
                    Text("·").foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                    Text(reset).font(Theme.Font.body).foregroundStyle(Theme.textSecondary)
                }
                Spacer(minLength: Theme.Space.m)
                if let used = NotebookList.allowanceUsedFraction(quota) {
                    MainAllowanceBar(fraction: used)
                        .frame(width: 140, height: 5)
                        .accessibilityHidden(true)
                }
            }
            .lineLimit(1)
            .accessibilityElement(children: .combine)
        }
    }
}

/// Share of the month's pages used. Decorative: the text next to it says the same thing.
struct MainAllowanceBar: View {
    let fraction: Double

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.surfaceSunken)
                Capsule().fill(fraction >= 0.9 ? Theme.warning : Theme.textSecondary)
                    .frame(width: max(proxy.size.height, proxy.size.width * fraction))
            }
        }
        .overlay(Capsule().strokeBorder(Theme.border, lineWidth: 0.5))
    }
}

/// A borderless icon button for quiet header actions.
struct MainIconButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Theme.textSecondary)
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(configuration.isPressed ? Theme.surfaceSunken : Color.clear)
            )
            .contentShape(Rectangle())
    }
}
