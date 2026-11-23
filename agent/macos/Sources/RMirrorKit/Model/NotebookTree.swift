import Foundation

/// One thing in the notebook outline.
public enum TreeItem: Hashable, Sendable {
    case folder(String)
    case notebook(String)
}

/// A row the list shows: what it is and how deep it sits (0 at the top level).
public struct TreeRow: Identifiable, Hashable, Sendable {
    public let item: TreeItem
    public let depth: Int

    public var id: TreeItem { item }

    public init(item: TreeItem, depth: Int) {
        self.item = item
        self.depth = depth
    }
}

/// A folder's checkbox: nothing below it ticked, some, or all.
public enum TickState: Equatable, Sendable {
    case none, mixed, all
}

/// Keys the notebook list handles while it has keyboard focus.
public enum ListKey: Equatable, Sendable {
    case up, down, left, right, space, enter
}

/// What a key press does: the new highlighted row, the folders open afterwards, and a tick to flip
/// (for a folder: every notebook below it, as `NotebookTree.togglingFolder`).
public struct ListKeyOutcome: Equatable, Sendable {
    public var highlight: TreeItem?
    public var open: Set<String>
    public var toggle: TreeItem?

    public init(highlight: TreeItem?, open: Set<String>, toggle: TreeItem? = nil) {
        self.highlight = highlight
        self.open = open
        self.toggle = toggle
    }
}

/// The reMarkable's folders and notebooks as an outline: built once per notebook reload, then asked
/// for the visible rows (per open set or search), folder tick counts (per selection change) and
/// keyboard moves. Never crashes on bad data: a notebook or folder whose parent is unknown, and every
/// folder in a parent loop, is placed at the top level.
public struct NotebookTree: Sendable {
    public struct Folder: Equatable, Sendable {
        public let id: String
        public let name: String
        /// nil at the top level (also for folders moved there because their parent was unknown or a loop).
        public let parentID: String?
        public let depth: Int
        /// Sorted A to Z.
        public let childFolderIDs: [String]
        /// The notebooks directly in this folder, sorted A to Z.
        public let notebookIDs: [String]
        /// Notebooks below this folder at any depth.
        public let totalNotebooks: Int

        public var hasChildren: Bool { !childFolderIDs.isEmpty || !notebookIDs.isEmpty }
    }

    public let folders: [String: Folder]
    public let topFolderIDs: [String]
    public let topNotebookIDs: [String]
    public let notebooks: [String: NotebookEntry]
    /// Every notebook in outline order (depth first, folders before notebooks at each level).
    public let notebookOrder: [String]
    /// Every notebook in "Recent" order (`RecentList.isOrderedBefore`).
    public let recentOrder: [String]
    /// The folder directly holding each notebook that is in a folder.
    private let notebookParent: [String: String]
    private let paths: [String: [String]]
    private let searchKeys: [String: String]

    public static let empty = NotebookTree(folders: [], notebooks: [])

    public var isEmpty: Bool { notebooks.isEmpty && folders.isEmpty }

    public init(folders rawFolders: [FolderEntry], notebooks rawNotebooks: [NotebookEntry]) {
        // A core that does not send folders: work them out from the folder paths.
        let synthesized = rawFolders.isEmpty
        let folderEntries = synthesized ? Self.synthesizedFolders(from: rawNotebooks) : rawFolders

        var entries: [String: FolderEntry] = [:]
        for folder in folderEntries where entries[folder.uuid] == nil { entries[folder.uuid] = folder }

        // Parents that exist (a folder that is its own parent has none), then loops broken: every folder
        // in a loop goes to the top level.
        var parent: [String: String] = [:]
        for (id, folder) in entries {
            if let p = folder.parentUUID, p != id, entries[p] != nil { parent[id] = p }
        }
        var finished = Set<String>()
        for start in entries.keys.sorted() where !finished.contains(start) {
            var path: [String] = []
            var onPath: [String: Int] = [:]
            var current: String? = start
            while let id = current, !finished.contains(id) {
                if let index = onPath[id] {
                    for looped in path[index...] { parent[looped] = nil }
                    break
                }
                onPath[id] = path.count
                path.append(id)
                current = parent[id]
            }
            finished.formUnion(path)
        }

        var notebookByID: [String: NotebookEntry] = [:]
        var notebookParent: [String: String] = [:]
        for notebook in rawNotebooks where notebookByID[notebook.uuid] == nil {
            notebookByID[notebook.uuid] = notebook
            let p = synthesized
                ? (notebook.folderPath.isEmpty ? nil : Self.synthesizedID(notebook.folderPath))
                : notebook.parentUUID
            if let p, entries[p] != nil { notebookParent[notebook.uuid] = p }
        }

        var childFolders: [String: [String]] = [:]
        var topFolders: [String] = []
        for id in entries.keys {
            if let p = parent[id] { childFolders[p, default: []].append(id) } else { topFolders.append(id) }
        }
        var childNotebooks: [String: [String]] = [:]
        var topNotebooks: [String] = []
        for id in notebookByID.keys {
            if let p = notebookParent[id] { childNotebooks[p, default: []].append(id) } else { topNotebooks.append(id) }
        }

        let folderKeys = entries.mapValues { NotebookList.normalize($0.name) }
        let notebookKeys = notebookByID.mapValues { NotebookList.normalize($0.name) }
        func byName(_ keys: [String: String], _ names: @escaping (String) -> String) -> (String, String) -> Bool {
            { a, b in
                let order = keys[a]!.localizedStandardCompare(keys[b]!)
                if order != .orderedSame { return order == .orderedAscending }
                let exact = names(a).localizedStandardCompare(names(b))
                if exact != .orderedSame { return exact == .orderedAscending }
                return a < b
            }
        }
        let folderOrder = byName(folderKeys) { entries[$0]!.name }
        let notebookNameOrder = byName(notebookKeys) { notebookByID[$0]!.name }

        var built: [String: Folder] = [:]
        var order: [String] = []
        order.reserveCapacity(notebookByID.count)
        var paths: [String: [String]] = [:]

        /// Depth first; returns the number of notebooks below `id`.
        func build(_ id: String, depth: Int, path: [String]) -> Int {
            let entry = entries[id]!
            let folderPath = path + [entry.name]
            let subfolders = (childFolders[id] ?? []).sorted(by: folderOrder)
            let own = (childNotebooks[id] ?? []).sorted(by: notebookNameOrder)
            var total = own.count
            for child in subfolders { total += build(child, depth: depth + 1, path: folderPath) }
            for notebook in own {
                order.append(notebook)
                paths[notebook] = folderPath
            }
            built[id] = Folder(id: id, name: entry.name, parentID: parent[id], depth: depth,
                               childFolderIDs: subfolders, notebookIDs: own, totalNotebooks: total)
            return total
        }
        // Notebooks are appended after their folder's subfolders, which is outline order.
        let sortedTop = topFolders.sorted(by: folderOrder)
        for id in sortedTop { _ = build(id, depth: 0, path: []) }
        let sortedTopNotebooks = topNotebooks.sorted(by: notebookNameOrder)
        order.append(contentsOf: sortedTopNotebooks)
        // A notebook whose folder is unknown still has its folder path from the core.
        for id in sortedTopNotebooks { paths[id] = notebookByID[id]!.folderPath }

        self.folders = built
        self.topFolderIDs = sortedTop
        self.topNotebookIDs = sortedTopNotebooks
        self.notebooks = notebookByID
        self.notebookOrder = order
        self.recentOrder = notebookByID.values.sorted(by: RecentList.isOrderedBefore).map(\.uuid)
        self.notebookParent = notebookParent
        self.paths = paths
        self.searchKeys = Dictionary(uniqueKeysWithValues: notebookByID.map { id, notebook in
            (id, NotebookList.normalize(([notebook.name] + (paths[id] ?? [])).joined(separator: " ")))
        })
    }

    // MARK: Folders from paths

    /// Stable id for a folder known only by its path.
    public static func synthesizedID(_ path: [String]) -> String {
        "path:" + path.joined(separator: "\u{1F}")
    }

    /// Folders worked out from the notebooks' folder paths, for a core that does not send folders.
    public static func synthesizedFolders(from notebooks: [NotebookEntry]) -> [FolderEntry] {
        var seen = Set<String>()
        var result: [FolderEntry] = []
        for notebook in notebooks {
            for length in notebook.folderPath.indices.map({ $0 + 1 }) {
                let prefix = Array(notebook.folderPath.prefix(length))
                let id = synthesizedID(prefix)
                guard seen.insert(id).inserted else { continue }
                result.append(FolderEntry(uuid: id, name: prefix[length - 1],
                                          parentUUID: length > 1 ? synthesizedID(Array(prefix.dropLast())) : nil))
            }
        }
        return result
    }

    // MARK: Rows

    /// The outline as shown with `open` folders open.
    public func visibleRows(open: Set<String>) -> [TreeRow] {
        var rows: [TreeRow] = []
        func add(_ id: String) {
            guard let folder = folders[id] else { return }
            rows.append(TreeRow(item: .folder(id), depth: folder.depth))
            guard open.contains(id) else { return }
            for child in folder.childFolderIDs { add(child) }
            for notebook in folder.notebookIDs { rows.append(TreeRow(item: .notebook(notebook), depth: folder.depth + 1)) }
        }
        for id in topFolderIDs { add(id) }
        for notebook in topNotebookIDs { rows.append(TreeRow(item: .notebook(notebook), depth: 0)) }
        return rows
    }

    /// Search results: matching notebooks in outline order, flat. Same rule as before: every word must
    /// appear in the name or the folder path, ignoring case and accents. Empty for a blank search.
    public func searchResults(_ query: String) -> [String] {
        let terms = NotebookList.searchTerms(query)
        guard !terms.isEmpty else { return [] }
        return notebookOrder.filter { matches($0, terms: terms) }
    }

    func matches(_ id: String, terms: [String]) -> Bool {
        guard let key = searchKeys[id] else { return false }
        return NotebookList.matches(key: key, terms: terms)
    }

    /// Folder names from the top down to the notebook.
    public func path(of notebookID: String) -> [String] { paths[notebookID] ?? [] }

    /// "Work › 2026", or nil at the top level.
    public func pathText(of notebookID: String, separator: String = " \u{203A} ") -> String? {
        let p = path(of: notebookID)
        return p.isEmpty ? nil : p.joined(separator: separator)
    }

    public func parent(of item: TreeItem) -> TreeItem? {
        switch item {
        case .folder(let id): return folders[id]?.parentID.map(TreeItem.folder)
        case .notebook(let id): return notebookParent[id].map(TreeItem.folder)
        }
    }

    /// The item itself if it is shown, else its closest shown folder (after folders were closed).
    public func nearestVisible(_ item: TreeItem, in visible: Set<TreeItem>) -> TreeItem? {
        var current: TreeItem? = item
        while let c = current {
            if visible.contains(c) { return c }
            current = parent(of: c)
        }
        return nil
    }

    // MARK: Open folders

    /// Every folder that has something in it ("Expand all").
    public var expandableFolderIDs: Set<String> {
        Set(folders.values.lazy.filter(\.hasChildren).map(\.id))
    }

    /// First run: the top-level folders holding a ticked notebook are open, everything else closed.
    public func defaultOpen(selected: Set<String>) -> Set<String> {
        let counts = selectedCounts(selected)
        return Set(topFolderIDs.filter { (counts[$0] ?? 0) > 0 })
    }

    /// Drops remembered folders that no longer exist.
    public func pruned(open: Set<String>) -> Set<String> {
        open.filter { folders[$0] != nil }
    }

    // MARK: Ticks

    /// Ticked notebooks below each folder, at any depth. One pass over the selection; folders with none are absent.
    public func selectedCounts(_ selection: Set<String>) -> [String: Int] {
        var counts: [String: Int] = [:]
        for id in selection {
            var folder = notebookParent[id]
            while let f = folder {
                counts[f, default: 0] += 1
                folder = folders[f]?.parentID
            }
        }
        return counts
    }

    public func tickState(_ folderID: String, counts: [String: Int]) -> TickState {
        let total = folders[folderID]?.totalNotebooks ?? 0
        let selected = counts[folderID] ?? 0
        if total == 0 || selected == 0 { return .none }
        return selected >= total ? .all : .mixed
    }

    /// Every notebook below a folder, at any depth, in outline order.
    public func notebookIDs(under folderID: String) -> [String] {
        var result: [String] = []
        func collect(_ id: String) {
            guard let folder = folders[id] else { return }
            for child in folder.childFolderIDs { collect(child) }
            result.append(contentsOf: folder.notebookIDs)
        }
        collect(folderID)
        return result
    }

    /// Ticking a folder: if every notebook below it is ticked, untick them all; otherwise tick them all.
    /// Only the notebooks there now; one added to the folder later is not ticked by this.
    public func togglingFolder(_ folderID: String, in draft: Set<String>) -> Set<String> {
        let ids = notebookIDs(under: folderID)
        guard !ids.isEmpty else { return draft }
        return ids.allSatisfy(draft.contains) ? draft.subtracting(ids) : draft.union(ids)
    }

    // MARK: Keyboard

    /// Moves in the list. In a flat list (search results, "Recent") Left and Right do nothing and
    /// Return ticks like Space; in the outline Right opens a folder or steps into it, Left closes it or
    /// steps out to the parent, Space ticks (a folder: all below it) and Return opens or closes a folder.
    public func handle(_ key: ListKey, rows: [TreeRow], highlight: TreeItem?, open: Set<String>,
                       flat: Bool) -> ListKeyOutcome {
        var outcome = ListKeyOutcome(highlight: highlight, open: open)
        guard !rows.isEmpty else { outcome.highlight = nil; return outcome }
        let index = highlight.flatMap { h in rows.firstIndex { $0.item == h } }
        guard let index else {
            // Nothing highlighted yet: the arrows start at an end; other keys do nothing.
            switch key {
            case .down, .right: outcome.highlight = rows.first?.item
            case .up: outcome.highlight = rows.last?.item
            default: outcome.highlight = nil
            }
            return outcome
        }
        let row = rows[index]
        switch key {
        case .up:
            outcome.highlight = rows[max(0, index - 1)].item
        case .down:
            outcome.highlight = rows[min(rows.count - 1, index + 1)].item
        case .space:
            outcome.toggle = toggleTarget(row.item)
        case .enter:
            if case .folder(let id) = row.item, !flat {
                if folders[id]?.hasChildren == true { outcome.open = open.symmetricDifference([id]) }
            } else {
                outcome.toggle = toggleTarget(row.item)
            }
        case .right:
            guard !flat, case .folder(let id) = row.item, folders[id]?.hasChildren == true else { break }
            if !open.contains(id) {
                outcome.open.insert(id)
            } else if index + 1 < rows.count, rows[index + 1].depth > row.depth {
                outcome.highlight = rows[index + 1].item
            }
        case .left:
            guard !flat else { break }
            if case .folder(let id) = row.item, open.contains(id) {
                outcome.open.remove(id)
            } else if let up = parent(of: row.item) {
                outcome.highlight = up
            }
        }
        return outcome
    }

    private func toggleTarget(_ item: TreeItem) -> TreeItem? {
        if case .folder(let id) = item, (folders[id]?.totalNotebooks ?? 0) == 0 { return nil }
        return item
    }
}
