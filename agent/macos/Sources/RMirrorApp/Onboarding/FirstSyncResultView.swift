import RMirrorKit
import SwiftUI

/// The guided first sync finished. Shows what happened and where to go next.
struct FirstSyncResultView: View {
    @EnvironmentObject private var store: AppStore

    private var progress: SyncProgress { store.state?.sync ?? SyncProgress(state: .done) }

    private var isSuccess: Bool { progress.outcome == .success }

    /// The website's notebook list, if the core knows where the website is.
    private var dashboardURL: String? {
        guard let base = store.state?.environment.dashboardURL, !base.isEmpty else { return nil }
        let trimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        return trimmed + "/dashboard"
    }

    /// The notebooks the first sync used (the saved selection), for "Try again".
    private var selectedNotebookUUIDs: [String] {
        store.notebooks.filter(\.selected).map(\.uuid)
    }

    private var offersRetry: Bool {
        SharedCopy.resultOffersRetry(progress) && !selectedNotebookUUIDs.isEmpty
    }

    var body: some View {
        OnboardingScaffold(
            symbol: isSuccess ? "checkmark.circle" : "exclamationmark.circle",
            symbolTint: isSuccess ? Theme.success : Theme.warning,
            title: SharedCopy.resultTitle(progress)
        ) {
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                ForEach(SharedCopy.resultDetails(progress), id: \.self) { line in
                    Text(line)
                        .font(Theme.Font.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Text(OnboardingCopy.whatHappensNext)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        } actions: {
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                buttons
                OnboardingProblemLine(problem: store.problem)
            }
            .padding(.top, Theme.Space.s)
        }
        // The list loaded before the sync started; reload so the saved selection is current.
        .task { await store.reloadNotebooks() }
    }

    @ViewBuilder
    private var buttons: some View {
        HStack(spacing: Theme.Space.m) {
            if let dashboardURL {
                Button(OnboardingCopy.openOnWeb) { OnboardingSystem.open(dashboardURL) }
                    .buttonStyle(.rmPrimary)
                    .keyboardShortcut(.defaultAction)
                if offersRetry { retryButton }
                Button(OnboardingCopy.done) { store.finishGuidedSync() }
                    .buttonStyle(.rmSecondary)
                    .keyboardShortcut(.cancelAction)
            } else {
                Button(OnboardingCopy.done) { store.finishGuidedSync() }
                    .buttonStyle(.rmPrimary)
                    .keyboardShortcut(.defaultAction)
                if offersRetry { retryButton }
            }
        }
    }

    private var retryButton: some View {
        Button {
            let uuids = selectedNotebookUUIDs
            Task { await store.startGuidedSync(notebookUUIDs: uuids) }
        } label: {
            OnboardingBusyLabel(title: OnboardingCopy.tryAgain, busy: store.isStartingSync)
        }
        .buttonStyle(.rmSecondary)
        .disabled(store.isStartingSync)
    }
}
