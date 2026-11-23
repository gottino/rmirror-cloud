import RMirrorKit
import SwiftUI

/// The guided first sync (review finding B3): a sensible selection already made and one button.
struct FirstSyncView: View {
    @EnvironmentObject private var store: AppStore

    /// Notebook UUIDs the user has ticked.
    @State private var selection: Set<String> = []
    /// The suggestion (reason and notebooks) the selection was last filled from, so the store's
    /// refreshes never undo the user's ticks.
    @State private var seededFrom: [String]?
    @State private var choosing = false
    @State private var query = ""
    /// The search field has keyboard focus: Return then must not start the upload.
    @FocusState private var searchFocused: Bool
    /// Screenshot renderer only: ticks to start with.
    var previewSelection: Set<String>?

    // While the suggestion is not `.ok`, the store looks again every few seconds (`AppStore.refresh()`),
    // so this view needs no polling of its own.
    var body: some View {
        content
            .onAppear {
                seedSelection()
                if let previewSelection { selection = previewSelection }
            }
            .onChange(of: store.suggestion) { _ in seedSelection() }
    }

    @ViewBuilder
    private var content: some View {
        if let suggestion = store.suggestion {
            switch suggestion.reason {
            case .ok:
                if suggestion.notebooks.isEmpty && store.notebooks.isEmpty {
                    noNotebooks
                } else {
                    picker(suggestion, noPagesLeft: false)
                }
            case .noNotebooks:
                noNotebooks
            case .quotaExhausted:
                if suggestion.notebooks.isEmpty && store.notebooks.isEmpty {
                    noPagesLeftNothingToUpload
                } else {
                    picker(suggestion, noPagesLeft: true)
                }
            case .noneFit:
                // Opens in the full list with nothing ticked (see `seedSelection`).
                picker(suggestion, noPagesLeft: false)
            case .notSignedIn, .folderUnavailable, .unknown:
                OnboardingCentredWaiting(text: OnboardingCopy.preparing)
            }
        } else if store.suggestionUnreachable {
            OnboardingCentredNote(text: OnboardingCopy.suggestionUnreachable)
        } else {
            OnboardingCentredWaiting(text: OnboardingCopy.loadingSuggestion)
        }
    }

    // MARK: Screens

    private var noNotebooks: some View {
        OnboardingScaffold(title: OnboardingCopy.noNotebooksTitle, message: OnboardingCopy.noNotebooksMessage) {
            OnboardingWaitingLine(text: OnboardingCopy.waitingForNotebooks)
        }
    }

    private var noPagesLeftNothingToUpload: some View {
        OnboardingScaffold(title: OnboardingCopy.noPagesLeftTitle, message: OnboardingCopy.noPagesLeftNothingToUpload) {
            if let reset = resetLine {
                Text(reset).font(Theme.Font.bodyStrong)
            }
        }
    }

    private func picker(_ suggestion: FirstRunSuggestion, noPagesLeft: Bool) -> some View {
        OnboardingScaffold(
            title: pickerTitle(suggestion, noPagesLeft: noPagesLeft),
            message: pickerMessage(suggestion, noPagesLeft: noPagesLeft)
        ) {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                if choosing {
                    OnboardingAllNotebooksList(notebooks: allNotebooks(suggestion), query: $query,
                                               searchFocused: $searchFocused, isOn: binding(for:))
                    if !suggestion.notebooks.isEmpty {
                        Button(OnboardingCopy.backToSuggestion) { backToSuggestion(suggestion) }
                            .buttonStyle(.rmLink)
                    }
                } else {
                    if !suggestion.notebooks.isEmpty {
                        OnboardingSuggestedList(notebooks: suggestion.notebooks, isOn: binding(for:))
                    }
                    Button(OnboardingCopy.chooseDifferent) { choosing = true }
                        .buttonStyle(.rmLink)
                }
            }
        } actions: {
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                Button(action: startSync) {
                    OnboardingBusyLabel(title: buttonTitle(noPagesLeft: noPagesLeft), busy: store.isStartingSync)
                }
                .buttonStyle(.rmPrimary)
                .keyboardShortcut(WindowRules.defaultButtonsTakeKeys(searchFieldFocused: searchFocused) ? .defaultAction : nil)
                .disabled(blockedReason(noPagesLeft: noPagesLeft) != nil || store.isStartingSync)

                if let reason = blockedReason(noPagesLeft: noPagesLeft) {
                    Text(reason)
                        .font(Theme.Font.body)
                        .foregroundStyle(Theme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                } else if noPagesLeft {
                    Text(OnboardingCopy.noPagesLeftUploadNote(resetDay: store.state?.quota.flatMap { SharedCopy.resetDay($0) }))
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text(SharedCopy.allowanceUse(pages: selectedPages, remaining: remaining))
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                OnboardingProblemLine(problem: store.problem)
            }
            .padding(.top, Theme.Space.s)
        }
    }

    // MARK: Wording

    private func pickerTitle(_ suggestion: FirstRunSuggestion, noPagesLeft: Bool) -> String {
        if noPagesLeft { return OnboardingCopy.noPagesLeftTitle }
        if suggestion.reason == .noneFit { return OnboardingCopy.noneFitTitle }
        if choosing || suggestion.notebooks.isEmpty { return OnboardingCopy.chooseTitle }
        return OnboardingCopy.suggestionTitle(count: suggestion.notebooks.count)
    }

    private func pickerMessage(_ suggestion: FirstRunSuggestion, noPagesLeft: Bool) -> String {
        if noPagesLeft { return OnboardingCopy.noPagesLeftMessage }
        if suggestion.reason == .noneFit {
            return OnboardingCopy.noneFitMessage(remaining: suggestion.quota?.remaining ?? remaining ?? 0)
        }
        return choosing ? OnboardingCopy.chooseMessage : OnboardingCopy.suggestionMessage
    }

    private func buttonTitle(noPagesLeft: Bool) -> String {
        if noPagesLeft { return OnboardingCopy.uploadNowButton(notebooks: selection.count, pages: selectedPages) }
        return OnboardingCopy.syncButton(notebooks: selection.count, pages: selectedPages)
    }

    /// Why the button is disabled, or nil when it can be pressed.
    private func blockedReason(noPagesLeft: Bool) -> String? {
        if selection.isEmpty { return OnboardingCopy.nothingTicked }
        if !noPagesLeft, let remaining, selectedPages > remaining {
            return OnboardingCopy.overAllowance(remaining: remaining)
        }
        return nil
    }

    private var resetLine: String? {
        store.state?.quota.flatMap { SharedCopy.allowanceReset($0) }
    }

    // MARK: Numbers

    /// Pages left this month, or nil when unlimited or unknown.
    private var remaining: Int? {
        if let quota = store.state?.quota {
            if quota.isUnlimited { return nil }
            return quota.remaining ?? max(0, quota.limit - quota.used)
        }
        if let quota = store.suggestion?.quota, !quota.isUnlimited {
            return quota.remaining ?? 0
        }
        return nil
    }

    private var pageCounts: [String: Int] {
        var counts: [String: Int] = [:]
        for notebook in store.suggestion?.notebooks ?? [] { counts[notebook.uuid] = notebook.pageCount }
        for notebook in store.notebooks { counts[notebook.uuid] = notebook.pageCount }
        return counts
    }

    private var selectedPages: Int {
        let counts = pageCounts
        return selection.reduce(0) { $0 + (counts[$1] ?? 0) }
    }

    /// Every notebook for "Choose different notebooks". Falls back to the suggestion if the full
    /// list has not loaded yet.
    private func allNotebooks(_ suggestion: FirstRunSuggestion) -> [NotebookEntry] {
        if !store.notebooks.isEmpty { return store.notebooks }
        return suggestion.notebooks.map { NotebookEntry(uuid: $0.uuid, name: $0.name, pageCount: $0.pageCount) }
    }

    // MARK: Actions

    private func binding(for uuid: String) -> Binding<Bool> {
        Binding(
            get: { selection.contains(uuid) },
            set: { isOn in
                if isOn { selection.insert(uuid) } else { selection.remove(uuid) }
            }
        )
    }

    /// Fills the ticks from a new suggestion. `.noneFit` opens straight in the full list with
    /// nothing ticked, because no recent notebook fits the pages left.
    private func seedSelection() {
        guard let suggestion = store.suggestion else { return }
        let key = [suggestion.reason.rawValue] + suggestion.notebooks.map(\.uuid)
        guard seededFrom != key else { return }
        seededFrom = key
        selection = Set(suggestion.notebooks.map(\.uuid))
        choosing = suggestion.reason == .noneFit
        query = ""
    }

    private func backToSuggestion(_ suggestion: FirstRunSuggestion) {
        selection = Set(suggestion.notebooks.map(\.uuid))
        choosing = false
        query = ""
    }

    private func startSync() {
        let uuids = selection.sorted()
        Task { await store.startGuidedSync(notebookUUIDs: uuids) }
    }
}

/// A centred line without a spinner, for a wait that may last (rMirror keeps trying by itself).
struct OnboardingCentredNote: View {
    let text: String

    var body: some View {
        Text(text)
            .font(Theme.Font.body)
            .foregroundStyle(Theme.textSecondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: OnboardingLayout.columnWidth)
            .padding(Theme.Space.xl)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A centred spinner with a short line, for brief in-between moments.
struct OnboardingCentredWaiting: View {
    let text: String

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            ProgressView()
                .accessibilityHidden(true)
            Text(text)
                .font(Theme.Font.body)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(Theme.Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}
