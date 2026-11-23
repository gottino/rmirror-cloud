import XCTest
@testable import RMirrorKit

final class NotebookTreeTests: XCTestCase {
    private var library: NotebookTree {
        NotebookTree(folders: Fixtures.libraryNotebooks.folders, notebooks: Fixtures.libraryNotebooks.notebooks)
    }

    private func nb(_ id: String, _ name: String, parent: String? = nil, path: [String] = [],
                    selected: Bool = false) -> NotebookEntry {
        NotebookEntry(uuid: id, name: name, folderPath: path, parentUUID: parent, pageCount: 1, selected: selected)
    }

    private func names(_ tree: NotebookTree, _ rows: [TreeRow]) -> [String] {
        rows.map { row in
            let indent = String(repeating: "  ", count: row.depth)
            switch row.item {
            case .folder(let id): return indent + "[" + tree.folders[id]!.name + "]"
            case .notebook(let id): return indent + tree.notebooks[id]!.name
            }
        }
    }

    // MARK: Building and ordering

    func testFoldersFirstAToZThenNotebooksAtEveryLevel() {
        let tree = library
        XCTAssertEqual(names(tree, tree.visibleRows(open: [])),
                       ["[Home]", "[Reading]", "[Work]",
                        "Café Ideas", "Quick Notes", "Sketches", "Travel Journal"])
        let open: Set = ["f-work", "f-work-2026", "f-work-2026-clients", "f-work-2026-clients-acme"]
        XCTAssertEqual(names(tree, tree.visibleRows(open: open)), [
            "[Home]", "[Reading]",
            "[Work]",
            "  [2025]", "  [2026]",
            "    [Clients]",
            "      [Acme]",
            "        Acme discovery interviews and stakeholder mapping, second round",
            "      Kick-off Workshop",
            "    Meeting Notes", "    Product Roadmap",
            "  Ideas", "  Standup",
            "Café Ideas", "Quick Notes", "Sketches", "Travel Journal",
        ])
    }

    func testSortingIgnoresCaseAndAccents() {
        let folders = [FolderEntry(uuid: "b", name: "beta"), FolderEntry(uuid: "a", name: "Älpha"),
                       FolderEntry(uuid: "c", name: "Gamma")]
        // Each folder holds a notebook, because folders without notebooks are not shown.
        let notebooks = [nb("2", "zeta"), nb("1", "Éclair"), nb("3", "apple"),
                         nb("4", "in a", parent: "a"), nb("5", "in b", parent: "b"), nb("6", "in c", parent: "c")]
        let tree = NotebookTree(folders: folders, notebooks: notebooks)
        XCTAssertEqual(names(tree, tree.visibleRows(open: [])), ["[Älpha]", "[beta]", "[Gamma]", "apple", "Éclair", "zeta"])
    }

    func testSameNameFoldersStayApartAndEmptyFoldersAreKept() {
        let tree = library
        XCTAssertEqual(tree.folders["f-work-archive"]?.name, "Archive")
        XCTAssertEqual(tree.folders["f-home-archive"]?.name, "Archive")
        XCTAssertEqual(tree.folders["f-work-archive"]?.totalNotebooks, 0)
        XCTAssertEqual(tree.folders["f-home-archive"]?.totalNotebooks, 1)
        XCTAssertEqual(tree.folders["f-templates"]?.hasChildren, false)
        XCTAssertEqual(tree.folders["f-work"]?.totalNotebooks, 8)
        XCTAssertEqual(tree.folders["f-work-2026-clients-acme"]?.depth, 3)
        XCTAssertEqual(tree.notebookOrder.count, Fixtures.libraryNotebooks.notebooks.count)
    }

    func testOrphansAndLoopsGoToTheTopLevelWithoutCrashing() {
        let folders = [
            FolderEntry(uuid: "a", name: "A", parentUUID: "b"),
            FolderEntry(uuid: "b", name: "B", parentUUID: "a"),      // a <-> b loop
            FolderEntry(uuid: "c", name: "C", parentUUID: "a"),      // points into the loop: stays under A
            FolderEntry(uuid: "s", name: "Self", parentUUID: "s"),   // its own parent
            FolderEntry(uuid: "o", name: "Orphan", parentUUID: "gone"),
            FolderEntry(uuid: "o", name: "Duplicate id", parentUUID: nil),
        ]
        let notebooks = [nb("n1", "Lost", parent: "missing", path: ["Somewhere"]), nb("n2", "In C", parent: "c"),
                         nb("n1", "Duplicate notebook")]
        let tree = NotebookTree(folders: folders, notebooks: notebooks)
        XCTAssertEqual(tree.topFolderIDs, ["a", "b", "o", "s"])
        XCTAssertEqual(tree.folders["c"]?.parentID, "a")
        XCTAssertEqual(tree.topNotebookIDs, ["n1"])
        XCTAssertEqual(tree.pathText(of: "n1"), "Somewhere", "an orphan keeps the path the core sent")
        XCTAssertEqual(tree.pathText(of: "n2"), "A \u{203A} C")
        XCTAssertEqual(tree.notebookIDs(under: "a"), ["n2"])
        // Only A and C lead to a notebook; the folders without notebooks (B, Self, Orphan) are not shown.
        XCTAssertEqual(tree.visibleRows(open: tree.expandableFolderIDs).count, 4)
    }

    func testFoldersAreWorkedOutFromPathsWhenTheCoreSendsNone() {
        let tree = NotebookTree(folders: [], notebooks: Fixtures.readyNotebooks.notebooks)
        XCTAssertEqual(tree.topFolderIDs.map { tree.folders[$0]!.name }, ["Home", "Work"])
        let work = NotebookTree.synthesizedID(["Work"])
        let work2026 = NotebookTree.synthesizedID(["Work", "2026"])
        XCTAssertEqual(tree.folders[work2026]?.parentID, work)
        XCTAssertEqual(Set(tree.notebookIDs(under: work)), ["nb-meeting-notes", "nb-roadmap", "nb-standup", "nb-ideas"])
        XCTAssertEqual(tree.pathText(of: "nb-budget"), "Home \u{203A} Finance")
        // Stable: the same paths give the same ids on the next load.
        XCTAssertEqual(NotebookTree.synthesizedFolders(from: Fixtures.readyNotebooks.notebooks),
                       NotebookTree.synthesizedFolders(from: Fixtures.readyNotebooks.notebooks))
        XCTAssertNotEqual(NotebookTree.synthesizedID(["Home", "Archive"]), NotebookTree.synthesizedID(["Work", "Archive"]))
    }

    // MARK: Ticks

    func testCountsAndTriState() {
        let tree = library
        let saved = NotebookList.savedSelection(Fixtures.libraryNotebooks.notebooks)
        let counts = tree.selectedCounts(saved)
        XCTAssertEqual(counts["f-work"], 3)
        XCTAssertEqual(tree.folders["f-work"]?.totalNotebooks, 8)
        XCTAssertEqual(tree.tickState("f-work", counts: counts), .mixed)
        XCTAssertEqual(tree.tickState("f-work-2026-clients", counts: counts), .all)
        XCTAssertEqual(tree.tickState("f-work-2025", counts: counts), .none)
        XCTAssertEqual(tree.tickState("f-work-archive", counts: counts), .none, "an empty folder is never ticked")
        XCTAssertEqual(tree.tickState("f-reading", counts: counts), .mixed)
    }

    func testTickingAFolderTicksOnlyTheNotebooksThereNow() {
        let tree = library
        let saved = NotebookList.savedSelection(Fixtures.libraryNotebooks.notebooks)
        let ticked = tree.togglingFolder("f-work", in: saved)
        XCTAssertEqual(tree.tickState("f-work", counts: tree.selectedCounts(ticked)), .all, "mixed ticks all")
        XCTAssertTrue(ticked.isSuperset(of: saved))
        let unticked = tree.togglingFolder("f-work", in: ticked)
        XCTAssertEqual(tree.tickState("f-work", counts: tree.selectedCounts(unticked)), .none, "all unticks all")
        XCTAssertTrue(unticked.contains("nb-budget"), "other folders keep their ticks")
        XCTAssertEqual(tree.togglingFolder("f-work-archive", in: saved), saved)
        // The footer maths is unchanged: a folder tick is the same draft as ticking each notebook.
        let oneByOne = tree.notebookIDs(under: "f-work").reduce(saved) { $0.union([$1]) }
        XCTAssertEqual(NotebookList.diff(Fixtures.libraryNotebooks.notebooks, saved: saved, draft: ticked),
                       NotebookList.diff(Fixtures.libraryNotebooks.notebooks, saved: saved, draft: oneByOne))
    }

    // MARK: Open folders

    func testDefaultOpenAndPruning() {
        let tree = library
        let saved = NotebookList.savedSelection(Fixtures.libraryNotebooks.notebooks)
        XCTAssertEqual(tree.defaultOpen(selected: saved), ["f-work", "f-home", "f-reading"])
        XCTAssertEqual(tree.pruned(open: ["f-work", "gone", "f-work-2026"]), ["f-work", "f-work-2026"])
        XCTAssertFalse(tree.expandableFolderIDs.contains("f-templates"))
        XCTAssertTrue(tree.expandableFolderIDs.contains("f-work-2026-clients-acme"))
    }

    func testNearestVisibleAfterClosing() {
        let tree = library
        let rows = Set(tree.visibleRows(open: ["f-work"]).map(\.item))
        XCTAssertEqual(tree.nearestVisible(.notebook("nb-kickoff"), in: rows), .folder("f-work-2026"))
        XCTAssertEqual(tree.nearestVisible(.notebook("nb-quick"), in: rows), .notebook("nb-quick"))
    }

    // MARK: Search

    func testSearchFlattensWithPaths() {
        let tree = library
        XCTAssertEqual(tree.searchResults("2026"), ["nb-acme-interviews", "nb-kickoff", "nb-meeting-notes", "nb-roadmap"])
        XCTAssertEqual(tree.searchResults("cafe"), ["nb-cafe"], "accents are ignored")
        XCTAssertEqual(tree.searchResults("archive letters"), ["nb-letters"], "every word, name or path")
        XCTAssertEqual(tree.searchResults("   "), [])
        XCTAssertEqual(tree.pathText(of: "nb-kickoff"), "Work \u{203A} 2026 \u{203A} Clients")
        XCTAssertNil(tree.pathText(of: "nb-quick"))
    }

    // MARK: Keyboard

    func testArrowKeysInTheOutline() {
        let tree = library
        var open: Set<String> = []
        var rows = tree.visibleRows(open: open)
        // Nothing highlighted: Down starts at the top.
        var out = tree.handle(.down, rows: rows, highlight: nil, open: open, flat: false)
        XCTAssertEqual(out.highlight, .folder("f-home"))
        // Right opens a closed folder, then steps into it.
        out = tree.handle(.right, rows: rows, highlight: .folder("f-work"), open: open, flat: false)
        XCTAssertEqual(out.open, ["f-work"])
        XCTAssertEqual(out.highlight, .folder("f-work"))
        open = out.open
        rows = tree.visibleRows(open: open)
        out = tree.handle(.right, rows: rows, highlight: .folder("f-work"), open: open, flat: false)
        XCTAssertEqual(out.highlight, .folder("f-work-2025"))
        // Left on a notebook goes to its folder; Left on an open folder closes it.
        out = tree.handle(.left, rows: rows, highlight: .notebook("nb-ideas"), open: open, flat: false)
        XCTAssertEqual(out.highlight, .folder("f-work"))
        out = tree.handle(.left, rows: rows, highlight: .folder("f-work"), open: open, flat: false)
        XCTAssertEqual(out.open, [])
        // Up and Down stop at the ends.
        out = tree.handle(.up, rows: rows, highlight: rows.first?.item, open: open, flat: false)
        XCTAssertEqual(out.highlight, rows.first?.item)
        out = tree.handle(.down, rows: rows, highlight: rows.last?.item, open: open, flat: false)
        XCTAssertEqual(out.highlight, rows.last?.item)
        // A folder without notebooks is not a row, so the keys can never land on it.
        XCTAssertFalse(rows.contains { $0.item == .folder("f-work-archive") })
    }

    func testFoldersWithoutNotebooksAreNotShown() {
        let tree = library
        let everything = Set(tree.folders.keys)
        let rows = tree.visibleRows(open: everything)
        let shownFolders = rows.compactMap { row -> String? in
            if case .folder(let id) = row.item { return id } else { return nil }
        }
        XCTAssertFalse(shownFolders.contains("f-work-archive"), "a folder with no notebooks is hidden")
        XCTAssertFalse(shownFolders.contains("f-templates"))
        XCTAssertTrue(shownFolders.contains("f-home-archive"), "a folder with a notebook is shown")
        XCTAssertTrue(shownFolders.allSatisfy { (tree.folders[$0]?.totalNotebooks ?? 0) > 0 })
        let shownNotebooks = rows.filter { if case .notebook = $0.item { return true } else { return false } }.count
        XCTAssertEqual(shownNotebooks, tree.notebookOrder.count, "every notebook is still reachable")
    }

    func testSpaceAndReturn() {
        let tree = library
        let rows = tree.visibleRows(open: ["f-work"])
        var out = tree.handle(.space, rows: rows, highlight: .folder("f-work"), open: ["f-work"], flat: false)
        XCTAssertEqual(out.toggle, .folder("f-work"))
        XCTAssertEqual(out.open, ["f-work"])
        out = tree.handle(.enter, rows: rows, highlight: .folder("f-work"), open: ["f-work"], flat: false)
        XCTAssertNil(out.toggle)
        XCTAssertEqual(out.open, [])
        out = tree.handle(.enter, rows: rows, highlight: .notebook("nb-ideas"), open: ["f-work"], flat: false)
        XCTAssertEqual(out.toggle, .notebook("nb-ideas"))
        out = tree.handle(.space, rows: rows, highlight: .folder("f-work-archive"), open: ["f-work"], flat: false)
        XCTAssertNil(out.toggle, "an empty folder has nothing to tick")
        out = tree.handle(.space, rows: rows, highlight: nil, open: ["f-work"], flat: false)
        XCTAssertNil(out.toggle)
    }

    func testFlatListIgnoresLeftAndRight() {
        let tree = library
        let rows = tree.searchResults("work").map { TreeRow(item: .notebook($0), depth: 0) }
        let first = rows[0].item
        XCTAssertEqual(tree.handle(.right, rows: rows, highlight: first, open: [], flat: true),
                       ListKeyOutcome(highlight: first, open: []))
        XCTAssertEqual(tree.handle(.left, rows: rows, highlight: first, open: [], flat: true),
                       ListKeyOutcome(highlight: first, open: []))
        XCTAssertEqual(tree.handle(.enter, rows: rows, highlight: first, open: [], flat: true).toggle, first)
        XCTAssertEqual(tree.handle(.down, rows: rows, highlight: first, open: [], flat: true).highlight, rows[1].item)
        XCTAssertNil(tree.handle(.down, rows: [], highlight: first, open: [], flat: true).highlight)
    }

    // MARK: Size

    func testLargeLibraryBuildsQuickly() {
        var folders: [FolderEntry] = []
        for top in 0..<30 {
            folders.append(FolderEntry(uuid: "t\(top)", name: "Folder \(top)"))
            for sub in 0..<10 { folders.append(FolderEntry(uuid: "t\(top)s\(sub)", name: "Sub \(sub)", parentUUID: "t\(top)")) }
        }
        let notebooks = (0..<2_500).map { i in
            nb("n\(i)", "Notebook \(i)", parent: i % 7 == 0 ? nil : "t\(i % 30)s\(i % 10)", selected: i % 3 == 0)
        }
        let start = Date()
        let tree = NotebookTree(folders: folders, notebooks: notebooks)
        let all = Set(notebooks.map(\.uuid))
        let counts = tree.selectedCounts(all)
        let rows = tree.visibleRows(open: tree.expandableFolderIDs)
        let foldersWithNotebooks = folders.filter { (tree.folders[$0.uuid]?.totalNotebooks ?? 0) > 0 }.count
        XCTAssertEqual(rows.count, 2_500 + foldersWithNotebooks)
        XCTAssertEqual(counts["t0"], tree.folders["t0"]?.totalNotebooks)
        XCTAssertLessThan(Date().timeIntervalSince(start), 2, "debug build; release is far quicker")
    }
}

final class RecentListTests: XCTestCase {
    private let base = Fixtures.now

    private func nb(_ id: String, _ name: String = "N", modified: TimeInterval? = nil, opened: TimeInterval? = nil,
                    selected: Bool = false, synced: Int = 0) -> NotebookEntry {
        NotebookEntry(uuid: id, name: name, pageCount: 10,
                      lastOpenedAt: opened.map { base.addingTimeInterval(-$0) },
                      lastModifiedAt: modified.map { base.addingTimeInterval(-$0) },
                      selected: selected, syncedPages: synced)
    }

    func testNewestChangeFirstThenOpenedThenNameUndatedLast() {
        let notebooks = [
            nb("old", "Old", modified: 900),
            nb("undated", "A undated"),
            nb("opened", "Opened only", opened: 100),           // no modified date: falls back to opened
            nb("new", "New", modified: 10, opened: 5_000),      // modified wins over opened
            nb("tie-b", "B", modified: 500), nb("tie-a", "a", modified: 500),
        ]
        let tree = NotebookTree(folders: [], notebooks: notebooks)
        XCTAssertEqual(tree.recentOrder, ["new", "opened", "tie-a", "tie-b", "old", "undated"])
    }

    func testSyncedOnlyRule() {
        let saved: Set = ["s"]
        let notebooks = [nb("s", selected: true), nb("u", synced: 3), nb("d"), nb("k"), nb("x")]
        let tree = NotebookTree(folders: [], notebooks: notebooks)
        // Saved ticks and uploaded pages always; a fresh tick in the unsaved change too; `kept` rows stay.
        let shown = RecentList.visible(tree, query: "", syncedOnly: true, saved: saved, draft: ["s", "d"], kept: ["k"])
        XCTAssertEqual(Set(shown), ["s", "u", "d", "k"])
        // A saved notebook unticked in the draft is still synced until saved, so it stays.
        XCTAssertTrue(RecentList.visible(tree, query: "", syncedOnly: true, saved: saved, draft: [], kept: []).contains("s"))
        XCTAssertEqual(RecentList.visible(tree, query: "", syncedOnly: false, saved: saved, draft: [], kept: []).count, 5)
    }

    func testSearchKeepsDateOrder() {
        let tree = NotebookTree(folders: Fixtures.libraryNotebooks.folders, notebooks: Fixtures.libraryNotebooks.notebooks)
        XCTAssertEqual(RecentList.visible(tree, query: "work", syncedOnly: false, saved: [], draft: [], kept: []),
                       ["nb-meeting-notes", "nb-standup", "nb-kickoff", "nb-roadmap", "nb-ideas", "nb-acme-interviews",
                        "nb-quarterly", "nb-standup-2025"])
        let saved = NotebookList.savedSelection(Fixtures.libraryNotebooks.notebooks)
        XCTAssertEqual(RecentList.visible(tree, query: "work", syncedOnly: true, saved: saved, draft: saved, kept: []),
                       ["nb-meeting-notes", "nb-kickoff", "nb-acme-interviews", "nb-quarterly"])
    }

    func testPreferencesRoundTrip() throws {
        let suite = "rmirror.tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertEqual(NotebookListPreferences.load(from: defaults), NotebookListPreferences())
        let prefs = NotebookListPreferences(view: .recent, syncedOnly: true, open: ["f-work", "f-home"])
        prefs.save(to: defaults)
        XCTAssertEqual(NotebookListPreferences.load(from: defaults), prefs)
        NotebookListPreferences(open: []).save(to: defaults)
        XCTAssertEqual(NotebookListPreferences.load(from: defaults).open, [], "nothing open is remembered, not a first run")
    }
}
