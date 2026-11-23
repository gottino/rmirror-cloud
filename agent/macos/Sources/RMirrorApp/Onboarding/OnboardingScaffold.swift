import AppKit
import RMirrorKit
import SwiftUI

/// The frame every onboarding screen shares: a centred column (about 500 pt wide) with an
/// optional symbol, a title, a short message, the screen's content and its actions.
/// Scrolls when the window is too small; centres vertically when there is room.
struct OnboardingScaffold<Content: View, Actions: View>: View {
    var symbol: String?
    var symbolTint: Color
    let title: String
    var message: String?
    let content: Content
    let actions: Actions

    init(
        symbol: String? = nil,
        symbolTint: Color = Theme.accent,
        title: String,
        message: String? = nil,
        @ViewBuilder content: () -> Content,
        @ViewBuilder actions: () -> Actions
    ) {
        self.symbol = symbol
        self.symbolTint = symbolTint
        self.title = title
        self.message = message
        self.content = content()
        self.actions = actions()
    }

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.l) {
                    header
                    content
                    actions
                }
                .frame(maxWidth: OnboardingLayout.columnWidth, alignment: .leading)
                .padding(.horizontal, Theme.Space.xl)
                .padding(.vertical, Theme.Space.xl)
                .frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) {
            if let symbol {
                Image(systemName: symbol)
                    .font(.system(size: 30, weight: .regular))
                    .foregroundStyle(symbolTint)
                    .padding(.bottom, Theme.Space.xs)
                    .accessibilityHidden(true)
            }
            Text(title)
                .font(Theme.Font.title)
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let message {
                Text(message)
                    .font(Theme.Font.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

extension OnboardingScaffold where Actions == EmptyView {
    init(
        symbol: String? = nil,
        symbolTint: Color = Theme.accent,
        title: String,
        message: String? = nil,
        @ViewBuilder content: () -> Content
    ) {
        self.init(symbol: symbol, symbolTint: symbolTint, title: title, message: message, content: content) {
            EmptyView()
        }
    }
}

enum OnboardingLayout {
    static let columnWidth: CGFloat = 500
}

/// One numbered step: a number in a small circle, the instruction, and optional controls under it.
struct OnboardingStep<Accessory: View>: View {
    let number: Int
    let text: String
    let accessory: Accessory

    init(number: Int, text: String, @ViewBuilder accessory: () -> Accessory) {
        self.number = number
        self.text = text
        self.accessory = accessory()
    }

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Space.m) {
            Text("\(number)")
                .font(Theme.Font.label)
                .foregroundStyle(Theme.text)
                .frame(width: 22, height: 22)
                .background(Circle().fill(Theme.surfaceSunken))
                .overlay(Circle().strokeBorder(Theme.border))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                Text(text)
                    .font(Theme.Font.body)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Step \(number): \(text)")
                accessory
            }
            Spacer(minLength: 0)
        }
    }
}

extension OnboardingStep where Accessory == EmptyView {
    init(number: Int, text: String) {
        self.init(number: number, text: text) { EmptyView() }
    }
}

/// A quiet "still waiting" line: a small spinner and words.
struct OnboardingWaitingLine: View {
    let text: String

    var body: some View {
        HStack(spacing: Theme.Space.s) {
            ProgressView().controlSize(.small)
            Text(text)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The last action's problem, in words, near the button that caused it.
struct OnboardingProblemLine: View {
    let problem: ActionProblem?

    var body: some View {
        if let problem {
            Text(SharedCopy.problem(problem))
                .font(Theme.Font.body)
                .foregroundStyle(Theme.danger)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// A primary button label that shows a small spinner while its action runs.
struct OnboardingBusyLabel: View {
    let title: String
    let busy: Bool

    var body: some View {
        HStack(spacing: Theme.Space.s) {
            if busy {
                ProgressView().controlSize(.small)
            }
            Text(title)
        }
    }
}

/// System actions the onboarding screens need. Nothing here talks to the core.
enum OnboardingSystem {
    static func open(_ string: String) {
        guard let url = URL(string: string) else { return }
        NSWorkspace.shared.open(url)
    }

    /// True when running from an .app bundle, so the app can be reopened by path.
    static var canRelaunch: Bool { Bundle.main.bundlePath.hasSuffix(".app") }

    /// Quits this copy and opens a fresh one. The new copy waits until this one (and with it
    /// the core) has exited, so the two never compete for the core's port.
    static func relaunch() {
        guard canRelaunch else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = [
            "-c",
            "while kill -0 \"$1\" 2>/dev/null; do sleep 0.2; done; exec /usr/bin/open -n \"$2\"",
            "sh",
            String(ProcessInfo.processInfo.processIdentifier),
            Bundle.main.bundlePath,
        ]
        do {
            try process.run()
        } catch {
            return
        }
        NSApp.terminate(nil)
    }
}
