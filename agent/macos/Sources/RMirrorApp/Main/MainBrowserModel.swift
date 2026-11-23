import RMirrorKit
import SwiftUI

/// The notebook list's local state: the search, the grouped rows it shows, and the selection being edited.
/// Grouping is rebuilt only when the notebooks or the search change, never on other window updates.
@MainActor
final class MainBrowserModel: ObservableObject {
    @Published var query = "" {
        didSet { if query != oldValue { regroup() } }
    }
    @Published private(set) var groups: [NotebookGroup] = []
    /// The selection as the user is editing it. Sent to the core only on "Save" / "Save and sync".
    @Published private(set) var draft: Set<String> = []
    @Published private(set) var diff = SelectionDiff()

    private(set) var notebooks: [NotebookEntry] = []
    private(set) var saved: Set<String> = []
    private(set) var visibleIDs: [String] = []
    /// Page count per notebook, for "Sync again" on notebooks removed on the web.
    private(set) var pageCounts: [String: Int] = [:]
    private var index = NotebookIndex([])

    var hasNotebooks: Bool { !notebooks.isEmpty }
    var isSearching: Bool { !NotebookList.searchTerms(query).isEmpty }
    /// True when there is nothing left for "Select all" to tick (also when no rows are shown).
    var allVisibleSelected: Bool { visibleIDs.allSatisfy(draft.contains) }
    var noVisibleSelected: Bool { !visibleIDs.contains(where: draft.contains) }
    /// The draft in list order, for sending to the core.
    var selectionToSave: [String] { NotebookList.orderedSelection(notebooks, draft: draft) }

    /// Call whenever the store's notebooks change. Keeps an unsaved edit, dropping notebooks that disappeared.
    func update(_ newNotebooks: [NotebookEntry]) {
        guard newNotebooks != notebooks else { return }
        let hadEdits = !diff.isEmpty
        notebooks = newNotebooks
        saved = NotebookList.savedSelection(newNotebooks)
        draft = hadEdits ? NotebookList.reconciling(draft: draft, with: newNotebooks) : saved
        index = NotebookIndex(newNotebooks)
        pageCounts = Dictionary(newNotebooks.map { ($0.uuid, $0.pageCount) }, uniquingKeysWith: { first, _ in first })
        regroup()
        recomputeDiff()
    }

    func isSelected(_ uuid: String) -> Bool { draft.contains(uuid) }
    func isSaved(_ uuid: String) -> Bool { saved.contains(uuid) }

    func toggle(_ uuid: String) { setDraft(NotebookList.toggling(uuid, in: draft)) }
    func selectAllVisible() { setDraft(NotebookList.selectingAll(visibleIDs, in: draft)) }
    func selectNoneVisible() { setDraft(NotebookList.selectingNone(visibleIDs, in: draft)) }
    func cancel() { setDraft(saved) }
    /// Screenshot renderer only: start with a pending change so the footer shows.
    func replaceDraft(_ next: Set<String>) { setDraft(NotebookList.reconciling(draft: next, with: notebooks)) }

    /// After a successful save: treat the draft as saved until the reloaded notebooks confirm it.
    func markSaved() {
        saved = draft
        recomputeDiff()
    }

    private func setDraft(_ next: Set<String>) {
        guard next != draft else { return }
        draft = next
        recomputeDiff()
    }

    private func regroup() {
        groups = index.groups(matching: query)
        visibleIDs = groups.flatMap { $0.notebooks.map(\.uuid) }
    }

    private func recomputeDiff() {
        let next = NotebookList.diff(notebooks, saved: saved, draft: draft)
        if next != diff { diff = next }
    }
}
