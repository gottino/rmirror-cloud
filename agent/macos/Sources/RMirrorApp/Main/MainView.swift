import RMirrorKit
import SwiftUI

/// The main window after onboarding: account and status, the month's pages, any sync in progress,
/// and the notebook list with one place to save a changed choice.
struct MainView: View {
    @EnvironmentObject private var store: AppStore
    @StateObject private var browser = MainBrowserModel()

    /// A sync that finished with problems while this window was showing; cleared on dismiss or the next sync.
    @State private var finishedSync: SyncProgress?
    @State private var lastSyncState: SyncState?
    @State private var isSaving = false
    @State private var resolvingDeleted: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            top
                .padding(.horizontal, Theme.Space.l)
                .padding(.top, Theme.Space.l)
                .padding(.bottom, Theme.Space.m)
            Rectangle().fill(Theme.border).frame(height: 1)
            MainNotebookSection(
                browser: browser,
                loaded: store.notebooksLoaded,
                deleted: store.deletedNotebooks,
                resolvingDeleted: resolvingDeleted,
                onResolveDeleted: resolveDeleted
            )
            .frame(maxHeight: .infinity)
            if !browser.diff.isEmpty {
                MainFooter(
                    diff: browser.diff,
                    quota: store.state?.quota,
                    isSaving: isSaving,
                    isSyncRunning: isSyncRunning,
                    onCancel: { browser.cancel() },
                    onSave: { Task { await save() } }
                )
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.15), value: browser.diff.isEmpty)
        .task {
            browser.update(store.notebooks)
            lastSyncState = store.state?.sync.state
            await store.reloadNotebooks()
            await store.loadDeletedNotebooks()
        }
        .onChange(of: store.notebooks) { browser.update($0) }
        .onChange(of: store.state?.sync.state) { syncStateChanged(to: $0) }
    }

    // MARK: Top block

    private var top: some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            MainHeader(
                email: store.state?.auth.email,
                status: SharedCopy.statusLine(stage: store.stage, state: store.state),
                tone: MainStatus.tone(stage: store.stage, state: store.state),
                webURL: MainStatus.dashboardURL(store.state)
            )
            if let quota = store.state?.quota {
                MainAllowance(quota: quota, uploadsPaused: store.state?.queue.pausedReason == .quota)
            }
            notices
        }
    }

    @ViewBuilder
    private var notices: some View {
        if let state = store.state, state.sync.state == .running {
            MainSyncProgressStrip(counts: state.sync.counts)
        } else if let finishedSync {
            MainNotice(kind: .attention, systemImage: "exclamationmark.circle",
                       title: SharedCopy.resultTitle(finishedSync),
                       lines: SharedCopy.resultDetails(finishedSync, quota: store.state?.quota),
                       onDismiss: { self.finishedSync = nil }) {
                if SharedCopy.resultOffersRetry(finishedSync, quota: store.state?.quota) {
                    Button(MainCopy.tryAgain) { Task { await retrySync() } }
                        .buttonStyle(.rmSecondary)
                        .disabled(store.isStartingSync)
                }
            }
        }
        if let state = store.state, MainStatus.offersResume(state) {
            MainNotice(kind: .info, systemImage: "pause.circle", title: MainCopy.pausedTitle,
                       lines: [MainCopy.pausedBody]) {
                Button(MainCopy.tryAgain) { Task { await store.resumeSync() } }
                    .buttonStyle(.rmSecondary)
            }
        }
        if let problem = store.problem {
            MainNotice(kind: .problem, systemImage: "exclamationmark.triangle",
                       lines: [SharedCopy.problem(problem)],
                       onDismiss: { store.dismissProblem() })
        }
    }

    // MARK: Actions

    private var isSyncRunning: Bool { store.state?.sync.state == .running }

    private func save() async {
        guard !isSaving else { return }
        isSaving = true
        defer { isSaving = false }
        let selection = browser.selectionToSave
        let saved: Bool
        if browser.diff.onlyRemoves {
            saved = await store.saveSelection(notebookUUIDs: selection)
        } else {
            finishedSync = nil
            saved = await store.syncSelection(notebookUUIDs: selection)
        }
        if saved { browser.markSaved() }
    }

    /// "Try again" after a sync with failed pages: sync the saved choice again.
    private func retrySync() async {
        finishedSync = nil
        await store.syncSelection(notebookUUIDs: NotebookList.orderedSelection(browser.notebooks, draft: browser.saved))
    }

    private func resolveDeleted(_ uuid: String, _ action: DeletedNotebookAction) {
        resolvingDeleted.insert(uuid)
        Task {
            await store.resolveDeletedNotebook(uuid: uuid, action: action)
            resolvingDeleted.remove(uuid)
            if action == .resync { await store.reloadNotebooks() }
        }
    }

    private func syncStateChanged(to newState: SyncState?) {
        let previous = lastSyncState
        lastSyncState = newState
        if newState == .running {
            finishedSync = nil
            return
        }
        guard previous == .running else { return }
        // A sync just finished: show what went wrong, if anything, and pick up the new page counts.
        if let progress = store.state?.sync, progress.state == .done, MainStatus.showsResult(progress) {
            finishedSync = progress
        }
        Task { await store.reloadNotebooks() }
    }
}
