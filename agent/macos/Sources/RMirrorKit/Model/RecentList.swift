import Foundation

/// The "Recent" view of the notebook list: every notebook, flat, newest change on the reMarkable first.
public enum RecentList {
    /// When the notebook last changed: last modified, else last opened.
    public static func date(_ notebook: NotebookEntry) -> Date? {
        notebook.lastModifiedAt ?? notebook.lastOpenedAt
    }

    /// Newest first; notebooks without a date last; then by name; then by identifier so the order is stable.
    public static func isOrderedBefore(_ a: NotebookEntry, _ b: NotebookEntry) -> Bool {
        switch (date(a), date(b)) {
        case let (da?, db?) where da != db: return da > db
        case (_?, nil): return true
        case (nil, _?): return false
        default: break
        }
        let byName = a.name.localizedStandardCompare(b.name)
        if byName != .orderedSame { return byName == .orderedAscending }
        return a.uuid < b.uuid
    }

    /// Being synced: ticked in the saved selection, or with pages already in rMirror.
    public static func isSynced(_ notebook: NotebookEntry, saved: Set<String>) -> Bool {
        saved.contains(notebook.uuid) || notebook.syncedPages > 0
    }

    /// Whether "Synced only" shows a notebook. Synced notebooks, plus notebooks ticked in the unsaved
    /// change (so a tick made elsewhere shows up here too), plus `kept`: the rows that were on screen when
    /// the user last ticked or unticked something in this view, so nothing disappears under the pointer.
    /// `kept` is cleared when the filter is turned on again, the view changes or the notebooks reload.
    public static func showsWhenSyncedOnly(_ notebook: NotebookEntry, saved: Set<String>, draft: Set<String>,
                                           kept: Set<String>) -> Bool {
        isSynced(notebook, saved: saved) || draft.contains(notebook.uuid) || kept.contains(notebook.uuid)
    }

    /// The notebooks the Recent view shows, in date order.
    public static func visible(_ tree: NotebookTree, query: String, syncedOnly: Bool, saved: Set<String>,
                               draft: Set<String>, kept: Set<String>) -> [String] {
        let terms = NotebookList.searchTerms(query)
        return tree.recentOrder.filter { id in
            if !terms.isEmpty && !tree.matches(id, terms: terms) { return false }
            guard syncedOnly else { return true }
            guard let notebook = tree.notebooks[id] else { return false }
            return showsWhenSyncedOnly(notebook, saved: saved, draft: draft, kept: kept)
        }
    }
}

/// Which way the notebook list is shown.
public enum NotebookListView: String, CaseIterable, Sendable {
    case folders, recent
}

/// What the notebook list remembers between launches: the view, the "Synced only" filter, and which
/// folders are open (by folder id). `open == nil` means nothing remembered yet (first run).
public struct NotebookListPreferences: Equatable, Sendable {
    public var view: NotebookListView
    public var syncedOnly: Bool
    public var open: Set<String>?

    public init(view: NotebookListView = .folders, syncedOnly: Bool = false, open: Set<String>? = nil) {
        self.view = view
        self.syncedOnly = syncedOnly
        self.open = open
    }

    static let viewKey = "notebookList.view"
    static let syncedOnlyKey = "notebookList.syncedOnly"
    static let openKey = "notebookList.openFolders"

    public static func load(from defaults: UserDefaults) -> NotebookListPreferences {
        NotebookListPreferences(
            view: defaults.string(forKey: viewKey).flatMap(NotebookListView.init(rawValue:)) ?? .folders,
            syncedOnly: defaults.bool(forKey: syncedOnlyKey),
            open: (defaults.array(forKey: openKey) as? [String]).map(Set.init))
    }

    public func save(to defaults: UserDefaults) {
        defaults.set(view.rawValue, forKey: Self.viewKey)
        defaults.set(syncedOnly, forKey: Self.syncedOnlyKey)
        if let open { defaults.set(open.sorted(), forKey: Self.openKey) } else { defaults.removeObject(forKey: Self.openKey) }
    }
}
