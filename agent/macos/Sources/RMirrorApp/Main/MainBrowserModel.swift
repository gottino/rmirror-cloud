import RMirrorKit
import SwiftUI

/// Screenshot renderer only: how the list starts, instead of what was remembered.
struct MainListPreview {
    var view: NotebookListView = .folders
    var syncedOnly = false
    /// nil: the first-run default (top-level folders with a ticked notebook).
    var open: Set<String>?
    var query = ""
    var highlight: TreeItem?
    /// Draw the highlight as if the list had the keyboard.
    var keyboard = false
}

/// The notebook list's local state: the view, the search, which folders are open, the rows shown and
/// the selection being edited. The tree is built once per notebook reload; the rows are rebuilt only
/// when the view, the search, the open folders or the data change (and, with "Synced only", the ticks);
/// folder tick counts once per selection change.
@MainActor
final class MainBrowserModel: ObservableObject {
    @Published var query = "" {
        didSet { if query != oldValue { rebuildRows() } }
    }
    @Published private(set) var view: NotebookListView
    @Published private(set) var syncedOnly: Bool
    @Published private(set) var open: Set<String> = []
    @Published private(set) var rows: [TreeRow] = []
    /// The selection as the user is editing it. Sent to the core only on "Save" / "Save and sync".
    @Published private(set) var draft: Set<String> = []
    @Published private(set) var diff = SelectionDiff()
    /// Ticked notebooks below each folder, for the folder checkboxes and "2 of 5 selected".
    @Published private(set) var folderCounts: [String: Int] = [:]
    /// The row the arrow keys move; drawn only while the list has the keyboard.
    @Published var highlight: TreeItem?
    /// The list, not the search field or a button, takes the arrow keys, Space and Return.
    @Published var listHasKeyboard = false
    @Published private(set) var allVisibleSelected = true
    @Published private(set) var noVisibleSelected = true

    private(set) var tree = NotebookTree.empty
    private(set) var notebooks: [NotebookEntry] = []
    private(set) var saved: Set<String> = []
    /// Page count per notebook, for "Sync again" on notebooks removed on the web.
    private(set) var pageCounts: [String: Int] = [:]
    /// The clock for "3 days ago" (fixed in screenshots).
    let now: () -> Date

    private var folders: [FolderEntry] = []
    private var expandable: Set<String> = []
    /// Notebooks "Select all" / "Select none" act on: the search results or the Recent list, else every notebook.
    private var visibleNotebookIDs: [String] = []
    /// "Synced only": rows that were on screen when something was ticked here (see `RecentList`).
    private var kept: Set<String> = []
    private var rememberedOpen: Set<String>?
    private var openIsSet = false
    private let defaults: UserDefaults?
    private var pendingHighlight: TreeItem?

    /// - Parameter defaults: where the view, filter and open folders are remembered; nil remembers nothing.
    init(defaults: UserDefaults? = .standard, preview: MainListPreview? = nil, now: @escaping () -> Date = Date.init) {
        self.defaults = defaults
        self.now = now
        if let preview {
            view = preview.view
            syncedOnly = preview.syncedOnly
            rememberedOpen = preview.open
            query = preview.query
            pendingHighlight = preview.highlight
            listHasKeyboard = preview.keyboard
        } else {
            let prefs = defaults.map(NotebookListPreferences.load(from:)) ?? NotebookListPreferences()
            view = prefs.view
            syncedOnly = prefs.syncedOnly
            rememberedOpen = prefs.open
        }
    }

    var hasNotebooks: Bool { !notebooks.isEmpty }
    var isSearching: Bool { !NotebookList.searchTerms(query).isEmpty }
    /// The outline (not a flat list of search results or recent notebooks).
    var showsTree: Bool { view == .folders && !isSearching }
    /// The draft in list order, for sending to the core.
    var selectionToSave: [String] { NotebookList.orderedSelection(notebooks, draft: draft) }

    /// Call whenever the store's notebooks or folders change. Keeps an unsaved edit, dropping notebooks that disappeared.
    func update(_ newNotebooks: [NotebookEntry], folders newFolders: [FolderEntry]) {
        guard newNotebooks != notebooks || newFolders != folders else { return }
        let hadEdits = !diff.isEmpty
        notebooks = newNotebooks
        folders = newFolders
        tree = NotebookTree(folders: newFolders, notebooks: newNotebooks)
        expandable = tree.expandableFolderIDs
        saved = NotebookList.savedSelection(newNotebooks)
        draft = hadEdits ? NotebookList.reconciling(draft: draft, with: newNotebooks) : saved
        pageCounts = Dictionary(newNotebooks.map { ($0.uuid, $0.pageCount) }, uniquingKeysWith: { first, _ in first })
        kept = []
        settleOpenFolders()
        folderCounts = tree.selectedCounts(draft)
        rebuildRows()
        recomputeDiff()
        if let pendingHighlight, !rows.isEmpty {
            highlight = pendingHighlight
            self.pendingHighlight = nil
        }
    }

    // MARK: Ticks

    func isSelected(_ uuid: String) -> Bool { draft.contains(uuid) }
    func isSaved(_ uuid: String) -> Bool { saved.contains(uuid) }
    func tickState(_ folderID: String) -> TickState { tree.tickState(folderID, counts: folderCounts) }
    func selectedCount(_ folderID: String) -> Int { folderCounts[folderID] ?? 0 }

    func toggle(_ item: TreeItem) {
        keepRowsOnScreen()
        switch item {
        case .notebook(let id): setDraft(NotebookList.toggling(id, in: draft))
        case .folder(let id): setDraft(tree.togglingFolder(id, in: draft))
        }
    }

    func selectAllVisible() {
        keepRowsOnScreen()
        setDraft(NotebookList.selectingAll(visibleNotebookIDs, in: draft))
    }

    func selectNoneVisible() {
        keepRowsOnScreen()
        setDraft(NotebookList.selectingNone(visibleNotebookIDs, in: draft))
    }

    /// Ticks these notebooks in the draft, as if the user had ticked each one ("Tick them" in the notice
    /// after a catch-up). Nothing is saved or uploaded until "Save and sync".
    func tick(_ uuids: [String]) {
        guard !uuids.isEmpty else { return }
        keepRowsOnScreen()
        setDraft(NotebookList.selectingAll(uuids, in: draft))
    }

    func cancel() { setDraft(saved) }
    /// Screenshot renderer only: start with a pending change so the footer shows.
    func replaceDraft(_ next: Set<String>) { setDraft(NotebookList.reconciling(draft: next, with: notebooks)) }

    /// After a successful save: treat the draft as saved until the reloaded notebooks confirm it.
    func markSaved() {
        saved = draft
        recomputeDiff()
    }

    // MARK: View, filter and folders

    func setView(_ next: NotebookListView) {
        guard next != view else { return }
        view = next
        kept = []
        savePreferences()
        rebuildRows()
    }

    func setSyncedOnly(_ next: Bool) {
        guard next != syncedOnly else { return }
        syncedOnly = next
        kept = []
        savePreferences()
        rebuildRows()
    }

    func toggleOpen(_ folderID: String) { setOpen(open.symmetricDifference([folderID])) }
    func expandAll() { setOpen(expandable) }
    func collapseAll() { setOpen([]) }
    var canExpandAll: Bool { !expandable.isSubset(of: open) }
    var canCollapseAll: Bool { !open.isEmpty }

    // MARK: Keyboard

    func handleKey(_ key: ListKey) {
        let outcome = tree.handle(key, rows: rows, highlight: highlight, open: open, flat: !showsTree)
        if outcome.open != open { setOpen(outcome.open) }
        if outcome.highlight != highlight { highlight = outcome.highlight }
        if let item = outcome.toggle { toggle(item) }
    }

    /// From the search field (Down arrow): give the list the keyboard at its first row.
    func enterList() {
        listHasKeyboard = true
        if highlight == nil || !rows.contains(where: { $0.item == highlight }) { highlight = rows.first?.item }
    }

    // MARK: Private

    private func setDraft(_ next: Set<String>) {
        guard next != draft else { return }
        draft = next
        folderCounts = tree.selectedCounts(next)
        if view == .recent && syncedOnly { rebuildRows() } else { recomputeVisibleFlags() }
        recomputeDiff()
    }

    /// "Synced only": nothing on screen disappears because of a tick made here.
    private func keepRowsOnScreen() {
        guard view == .recent && syncedOnly else { return }
        kept.formUnion(visibleNotebookIDs)
    }

    private func setOpen(_ next: Set<String>) {
        guard next != open else { return }
        open = next
        savePreferences()
        rebuildRows()
    }

    /// First load: the remembered folders (pruned), or the first-run default. Later loads: prune.
    private func settleOpenFolders() {
        guard !tree.isEmpty else { return }
        let next: Set<String>
        if openIsSet {
            next = tree.pruned(open: open)
        } else {
            openIsSet = true
            next = rememberedOpen.map(tree.pruned(open:)) ?? tree.defaultOpen(selected: saved)
        }
        open = next
        if next != rememberedOpen {
            rememberedOpen = next
            savePreferences()
        }
    }

    private func savePreferences() {
        guard let defaults else { return }
        NotebookListPreferences(view: view, syncedOnly: syncedOnly, open: openIsSet ? open : rememberedOpen)
            .save(to: defaults)
    }

    private func rebuildRows() {
        let flatIDs: [String]
        switch (view, isSearching) {
        case (.folders, false):
            rows = tree.visibleRows(open: open)
            visibleNotebookIDs = tree.notebookOrder
            flatIDs = []
        case (.folders, true):
            flatIDs = tree.searchResults(query)
        case (.recent, _):
            flatIDs = RecentList.visible(tree, query: query, syncedOnly: syncedOnly, saved: saved, draft: draft, kept: kept)
        }
        if !showsTree {
            rows = flatIDs.map { TreeRow(item: .notebook($0), depth: 0) }
            visibleNotebookIDs = flatIDs
        }
        if let current = highlight {
            let shown = Set(rows.map(\.item))
            let next = showsTree ? tree.nearestVisible(current, in: shown) : (shown.contains(current) ? current : nil)
            if next != highlight { highlight = next }
        }
        recomputeVisibleFlags()
    }

    private func recomputeVisibleFlags() {
        let all = visibleNotebookIDs.allSatisfy(draft.contains)
        let none = !visibleNotebookIDs.contains(where: draft.contains)
        if all != allVisibleSelected { allVisibleSelected = all }
        if none != noVisibleSelected { noVisibleSelected = none }
    }

    private func recomputeDiff() {
        let next = NotebookList.diff(notebooks, saved: saved, draft: draft)
        if next != diff { diff = next }
    }
}
