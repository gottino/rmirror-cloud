import RMirrorKit
import SwiftUI

/// The guided first sync is running: live progress and the reassurance that closing is fine.
struct FirstSyncProgressView: View {
    @EnvironmentObject private var store: AppStore

    private var counts: SyncCounts { store.state?.sync.counts ?? SyncCounts() }

    var body: some View {
        OnboardingScaffold(title: OnboardingCopy.progressTitle) {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                progressBar
                HStack(alignment: .firstTextBaseline) {
                    Text(SharedCopy.progressLine(counts))
                        .font(Theme.Font.bodyStrong)
                        .monospacedDigit()
                    Spacer(minLength: Theme.Space.m)
                    if let notebookLine = SharedCopy.notebookProgressLine(counts) {
                        Text(notebookLine)
                            .font(Theme.Font.body)
                            .foregroundStyle(Theme.textSecondary)
                            .monospacedDigit()
                    }
                }
            }
            .rmCard()

            Text(OnboardingCopy.progressReassurance)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        } actions: {
            EmptyView()
        }
    }

    @ViewBuilder
    private var progressBar: some View {
        if let fraction = SharedCopy.progressFraction(counts) {
            ProgressView(value: fraction)
                .progressViewStyle(.linear)
                .tint(Theme.accent)
                .accessibilityLabel(SharedCopy.progressLine(counts))
        } else {
            ProgressView()
                .progressViewStyle(.linear)
                .tint(Theme.accent)
                .accessibilityLabel(SharedCopy.progressLine(counts))
        }
    }
}
