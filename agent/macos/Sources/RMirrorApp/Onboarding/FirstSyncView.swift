import RMirrorKit
import SwiftUI

/// The guided first sync (review finding B3): a sensible selection already made and one button.
struct FirstSyncView: View {
    @EnvironmentObject private var store: AppStore

    /// Notebook UUIDs the user has ticked.
    @State private var selection: Set<String> = []
    /// The suggestion the selection was last filled from, so polling never undoes the user's ticks.
    @State private var seededFrom: [String]?
    @State private var choosing = false
    @State private var query = ""

    static let waitingPollSeconds: UInt64 = 5

    var body: some View {
        content
            .onAppear(perform: seedSelection)
            .onChange(of: store.suggestion) { _ in seedSelection() }
            .task(id: needsWaiting) { await keepCheckingWhileWaiting() }
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
            case .notSignedIn, .folderUnavailable, .unknown:
                OnboardingCentredWaiting(text: OnboardingCopy.preparing)
            }
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
            message: pickerMessage(noPagesLeft: noPagesLeft)
        ) {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                if choosing {
                    OnboardingAllNotebooksList(notebooks: allNotebooks(suggestion), query: $query, isOn: binding(for:))
                    Button(OnboardingCopy.backToSuggestion) { backToSuggestion(suggestion) }
                        .buttonStyle(.rmLink)
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
                .keyboardShortcut(.defaultAction)
                .disabled(blockedReason(noPagesLeft: noPagesLeft) != nil || store.isStartingSync)

                if let reason = blockedReason(noPagesLeft: noPagesLeft) {
                    Text(reason)
                        .font(Theme.Font.body)
                        .foregroundStyle(Theme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                } else if noPagesLeft {
                    if let reset = resetLine {
                        Text(reset).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                    }
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
        if choosing || suggestion.notebooks.isEmpty { return OnboardingCopy.chooseTitle }
        return OnboardingCopy.suggestionTitle(count: suggestion.notebooks.count)
    }

    private func pickerMessage(noPagesLeft: Bool) -> String {
        if noPagesLeft { return OnboardingCopy.noPagesLeftMessage }
        return choosing ? OnboardingCopy.chooseMessage : OnboardingCopy.suggestionMessage
    }

    private func buttonTitle(noPagesLeft: Bool) -> String {
        if noPagesLeft { return OnboardingCopy.uploadNowButton(notebooks: selection.count) }
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

    private func seedSelection() {
        guard let suggestion = store.suggestion else { return }
        let uuids = suggestion.notebooks.map(\.uuid)
        guard seededFrom != uuids else { return }
        seededFrom = uuids
        selection = Set(uuids)
        choosing = false
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

    // MARK: Waiting

    /// True while the screen waits for something outside rMirror (notebooks, the folder, sign-in).
    private var needsWaiting: Bool {
        guard let suggestion = store.suggestion else { return true }
        switch suggestion.reason {
        case .ok, .quotaExhausted: return suggestion.notebooks.isEmpty && store.notebooks.isEmpty
        case .noNotebooks, .notSignedIn, .folderUnavailable, .unknown: return true
        }
    }

    /// The store loads the suggestion once per stage change; while waiting, ask again now and then
    /// so the screen moves on by itself.
    private func keepCheckingWhileWaiting() async {
        guard needsWaiting else { return }
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: Self.waitingPollSeconds * 1_000_000_000)
            if Task.isCancelled { return }
            await store.loadSuggestion()
            await store.reloadNotebooks()
        }
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
