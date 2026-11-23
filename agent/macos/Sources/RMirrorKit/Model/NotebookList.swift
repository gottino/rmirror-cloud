import Foundation

/// Notebooks under one top-level folder, or the notebooks at the top level (`folder == nil`).
public struct NotebookGroup: Identifiable, Equatable, Sendable {
    /// The top-level folder name; nil for notebooks that are not in a folder.
    public var folder: String?
    /// Sorted: most recently opened first (falling back to last modified), then by name.
    public var notebooks: [NotebookEntry]

    public var id: String { folder.map { "folder:\($0)" } ?? "top-level" }

    public init(folder: String?, notebooks: [NotebookEntry]) {
        self.folder = folder
        self.notebooks = notebooks
    }
}

/// How far a notebook's pages have reached rMirror.
public enum SyncIndicator: Equatable, Sendable {
    /// The notebook has no pages.
    case empty
    /// No page uploaded yet.
    case notSynced(total: Int)
    /// Some pages uploaded.
    case partly(synced: Int, total: Int)
    /// Every page uploaded.
    case complete(total: Int)
}

/// The difference between the saved selection and the one being edited.
public struct SelectionDiff: Equatable, Sendable {
    /// Newly ticked notebooks, in list order.
    public var added: [String]
    /// Newly unticked notebooks, in list order.
    public var removed: [String]
    /// Pages not uploaded yet in the newly ticked notebooks only.
    public var newPages: Int
    /// Pages "Save and sync" uploads: it syncs the whole ticked selection, so this counts the pages not
    /// uploaded yet in every ticked notebook, including ones that were already ticked. This is the
    /// number to show and to compare with the allowance.
    public var pagesToUpload: Int

    public init(added: [String] = [], removed: [String] = [], newPages: Int = 0, pagesToUpload: Int = 0) {
        self.added = added
        self.removed = removed
        self.newPages = newPages
        self.pagesToUpload = pagesToUpload
    }

    public var isEmpty: Bool { added.isEmpty && removed.isEmpty }
    /// True when the change only unticks notebooks: saving is enough, nothing new to sync.
    public var onlyRemoves: Bool { added.isEmpty && !removed.isEmpty }
}

/// Pure logic behind the main window's notebook list: search, grouping, sorting and selection maths.
public enum NotebookList {
    // MARK: Search

    /// Lower-cased, accent-free form used for matching ("Café" and "cafe" match).
    public static func normalize(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: nil)
    }

    /// The text a search looks at: the name and the whole folder path.
    public static func searchKey(_ notebook: NotebookEntry) -> String {
        normalize(([notebook.name] + notebook.folderPath).joined(separator: " "))
    }

    /// Search words; every word must appear (in any order) for a notebook to match.
    public static func searchTerms(_ query: String) -> [String] {
        normalize(query).split(whereSeparator: { $0.isWhitespace }).map(String.init)
    }

    public static func matches(_ notebook: NotebookEntry, query: String) -> Bool {
        matches(key: searchKey(notebook), terms: searchTerms(query))
    }

    static func matches(key: String, terms: [String]) -> Bool {
        terms.allSatisfy { key.contains($0) }
    }

    // MARK: Sorting and grouping

    /// The date used for "most recent": last opened, else last modified.
    public static func recency(_ notebook: NotebookEntry) -> Date? {
        notebook.lastOpenedAt ?? notebook.lastModifiedAt
    }

    /// Most recent first; notebooks without dates last; then by name; then by identifier so the order is stable.
    public static func isOrderedBefore(_ a: NotebookEntry, _ b: NotebookEntry) -> Bool {
        switch (recency(a), recency(b)) {
        case let (da?, db?) where da != db: return da > db
        case (_?, nil): return true
        case (nil, _?): return false
        default: break
        }
        let byName = a.name.localizedStandardCompare(b.name)
        if byName != .orderedSame { return byName == .orderedAscending }
        return a.uuid < b.uuid
    }

    /// Folders in alphabetical order, then the notebooks that are not in a folder (as the reMarkable app lists them).
    public static func grouped(_ notebooks: [NotebookEntry]) -> [NotebookGroup] {
        var byFolder: [String: [NotebookEntry]] = [:]
        var topLevel: [NotebookEntry] = []
        for notebook in notebooks {
            if let folder = notebook.folderPath.first {
                byFolder[folder, default: []].append(notebook)
            } else {
                topLevel.append(notebook)
            }
        }
        var groups = byFolder.keys
            .sorted { $0.localizedStandardCompare($1) == .orderedAscending }
            .map { NotebookGroup(folder: $0, notebooks: byFolder[$0]!.sorted(by: isOrderedBefore)) }
        if !topLevel.isEmpty {
            groups.append(NotebookGroup(folder: nil, notebooks: topLevel.sorted(by: isOrderedBefore)))
        }
        return groups
    }

    /// Filtered, then grouped and sorted. For many calls on the same notebooks use `NotebookIndex`.
    public static func groups(_ notebooks: [NotebookEntry], matching query: String) -> [NotebookGroup] {
        NotebookIndex(notebooks).groups(matching: query)
    }

    /// The folders below the top-level one, e.g. "2026" for Work › 2026, or nil.
    public static func subfolderPath(_ notebook: NotebookEntry, separator: String = " / ") -> String? {
        let rest = notebook.folderPath.dropFirst()
        return rest.isEmpty ? nil : rest.joined(separator: separator)
    }

    // MARK: Sync indicator

    public static func syncIndicator(_ notebook: NotebookEntry) -> SyncIndicator {
        let total = max(0, notebook.pageCount)
        let synced = min(max(0, notebook.syncedPages), total)
        if total == 0 { return .empty }
        if synced == 0 { return .notSynced(total: total) }
        if synced == total { return .complete(total: total) }
        return .partly(synced: synced, total: total)
    }

    /// Pages of this notebook not uploaded yet. `pageCount` is already capped by the saved page limit.
    public static func pagesToUpload(_ notebook: NotebookEntry) -> Int {
        max(0, notebook.pageCount - max(0, notebook.syncedPages))
    }

    // MARK: Selection

    /// The selection as saved in the core.
    public static func savedSelection(_ notebooks: [NotebookEntry]) -> Set<String> {
        Set(notebooks.lazy.filter(\.selected).map(\.uuid))
    }

    public static func diff(_ notebooks: [NotebookEntry], saved: Set<String>, draft: Set<String>) -> SelectionDiff {
        var result = SelectionDiff()
        for notebook in notebooks {
            let wasSelected = saved.contains(notebook.uuid)
            let isSelected = draft.contains(notebook.uuid)
            if isSelected { result.pagesToUpload += pagesToUpload(notebook) }
            if isSelected && !wasSelected {
                result.added.append(notebook.uuid)
                result.newPages += pagesToUpload(notebook)
            } else if wasSelected && !isSelected {
                result.removed.append(notebook.uuid)
            }
        }
        return result
    }

    /// The draft in list order, for sending to the core.
    public static func orderedSelection(_ notebooks: [NotebookEntry], draft: Set<String>) -> [String] {
        notebooks.lazy.map(\.uuid).filter { draft.contains($0) }
    }

    /// "Select all" for the rows currently visible; rows hidden by the search keep their state.
    public static func selectingAll(_ visible: [String], in draft: Set<String>) -> Set<String> {
        draft.union(visible)
    }

    /// The notebooks the server already has pages of that are not ticked in `draft`, in list order
    /// ("Tick them" in the notice after a catch-up).
    public static func onServerNotTicked(_ notebooks: [NotebookEntry], draft: Set<String>) -> [String] {
        notebooks.filter { $0.onServer && !draft.contains($0.uuid) }.map(\.uuid)
    }

    /// "Select none" for the rows currently visible; rows hidden by the search keep their state.
    public static func selectingNone(_ visible: [String], in draft: Set<String>) -> Set<String> {
        draft.subtracting(visible)
    }

    public static func toggling(_ uuid: String, in draft: Set<String>) -> Set<String> {
        var next = draft
        if next.contains(uuid) { next.remove(uuid) } else { next.insert(uuid) }
        return next
    }

    /// Keeps an in-progress draft valid after the notebooks reload: notebooks that disappeared are dropped.
    public static func reconciling(draft: Set<String>, with notebooks: [NotebookEntry]) -> Set<String> {
        draft.intersection(notebooks.lazy.map(\.uuid))
    }

    // MARK: Allowance

    /// Pages left this month, or nil when unlimited or unknown.
    public static func remainingPages(_ quota: QuotaInfo?) -> Int? {
        guard let quota, !quota.isUnlimited else { return nil }
        return max(0, quota.remaining ?? (quota.limit - quota.used))
    }

    /// Whether uploading `pages` more pages goes beyond this month's allowance. Never blocks; the app only warns.
    public static func exceedsAllowance(pages: Int, quota: QuotaInfo?) -> Bool {
        guard let remaining = remainingPages(quota) else { return false }
        return pages > remaining
    }

    /// 0...1 share of the allowance used, or nil when unlimited or unknown.
    public static func allowanceUsedFraction(_ quota: QuotaInfo?) -> Double? {
        guard let quota, !quota.isUnlimited, quota.limit > 0 else { return nil }
        let remaining = remainingPages(quota) ?? 0
        return min(1, max(0, Double(quota.limit - remaining) / Double(quota.limit)))
    }
}

/// Notebooks prepared once for repeated searching: sorted, grouped, with search keys computed.
/// Build it when the notebooks change; call `groups(matching:)` when the search changes.
public struct NotebookIndex: Sendable {
    private struct Entry: Sendable {
        let notebook: NotebookEntry
        let key: String
    }

    private struct Group: Sendable {
        let folder: String?
        let entries: [Entry]
    }

    private let allGroups: [Group]
    public let count: Int

    public init(_ notebooks: [NotebookEntry]) {
        count = notebooks.count
        allGroups = NotebookList.grouped(notebooks).map { group in
            Group(folder: group.folder,
                  entries: group.notebooks.map { Entry(notebook: $0, key: NotebookList.searchKey($0)) })
        }
    }

    public var isEmpty: Bool { count == 0 }

    public func groups(matching query: String) -> [NotebookGroup] {
        let terms = NotebookList.searchTerms(query)
        if terms.isEmpty {
            return allGroups.map { NotebookGroup(folder: $0.folder, notebooks: $0.entries.map(\.notebook)) }
        }
        return allGroups.compactMap { group in
            let hits = group.entries.filter { NotebookList.matches(key: $0.key, terms: terms) }.map(\.notebook)
            return hits.isEmpty ? nil : NotebookGroup(folder: group.folder, notebooks: hits)
        }
    }
}
