import XCTest
@testable import RMirrorKit

final class NotebookListTests: XCTestCase {
    private let base = Date(timeIntervalSince1970: 1_795_507_200)

    private func nb(_ id: String, _ name: String, _ path: [String] = [], pages: Int = 10, synced: Int = 0,
                    selected: Bool = false, opened: TimeInterval? = nil, modified: TimeInterval? = nil) -> NotebookEntry {
        NotebookEntry(uuid: id, name: name, folderPath: path, pageCount: pages,
                      lastOpenedAt: opened.map { base.addingTimeInterval(-$0) },
                      lastModifiedAt: modified.map { base.addingTimeInterval(-$0) },
                      selected: selected, syncedPages: synced)
    }

    // MARK: Search

    func testSearchIsCaseAndDiacriticInsensitiveOverNameAndPath() {
        let cafe = nb("a", "Café Notes", ["Privé", "Été"])
        XCTAssertTrue(NotebookList.matches(cafe, query: "cafe"))
        XCTAssertTrue(NotebookList.matches(cafe, query: "CAFÉ"))
        XCTAssertTrue(NotebookList.matches(cafe, query: "prive"))
        XCTAssertTrue(NotebookList.matches(cafe, query: "ete notes"), "words match in any order across name and path")
        XCTAssertFalse(NotebookList.matches(cafe, query: "garden"))
        XCTAssertTrue(NotebookList.matches(cafe, query: "   "), "blank search matches everything")
    }

    func testSearchOverFixtures() {
        let groups = NotebookList.groups(Fixtures.readyNotebooks.notebooks, matching: "work")
        XCTAssertEqual(groups.map(\.folder), ["Work"])
        XCTAssertEqual(groups.first?.notebooks.count, 4)
        XCTAssertTrue(NotebookList.groups(Fixtures.readyNotebooks.notebooks, matching: "zzz").isEmpty)
        let finance = NotebookList.groups(Fixtures.readyNotebooks.notebooks, matching: "finance")
        XCTAssertEqual(finance.flatMap(\.notebooks).map(\.uuid), ["nb-budget"])
    }

    // MARK: Grouping and sorting

    func testGroupsFoldersAlphabeticallyThenTopLevel() {
        let groups = NotebookList.grouped(Fixtures.readyNotebooks.notebooks)
        XCTAssertEqual(groups.map(\.folder), ["Home", "Work", nil])
        XCTAssertEqual(groups.map(\.id), ["folder:Home", "folder:Work", "top-level"])
        XCTAssertEqual(groups[1].notebooks.map(\.name), ["Meeting Notes", "Product Roadmap", "Standup", "Ideas"])
        XCTAssertEqual(groups[2].notebooks.map(\.name),
                       ["Book Club", "Travel Journal", "Reading List", "Sketches", "Quick Notes"])
    }

    func testSortFallsBackToModifiedThenName() {
        let list = [
            nb("1", "Zeta"),
            nb("2", "alpha"),
            nb("3", "Opened", opened: 500),
            nb("4", "Modified", modified: 100),
            nb("5", "Beta", opened: 100),
        ]
        let sorted = NotebookList.grouped(list)[0].notebooks.map(\.name)
        XCTAssertEqual(sorted, ["Beta", "Modified", "Opened", "alpha", "Zeta"])
    }

    func testSubfolderPath() {
        XCTAssertEqual(NotebookList.subfolderPath(nb("a", "A", ["Work", "2026", "Q4"])), "2026 / Q4")
        XCTAssertNil(NotebookList.subfolderPath(nb("a", "A", ["Work"])))
        XCTAssertNil(NotebookList.subfolderPath(nb("a", "A")))
    }

    func testIndexMatchesDirectGrouping() {
        let index = NotebookIndex(Fixtures.readyNotebooks.notebooks)
        XCTAssertEqual(index.count, 12)
        XCTAssertEqual(index.groups(matching: ""), NotebookList.grouped(Fixtures.readyNotebooks.notebooks))
        XCTAssertEqual(index.groups(matching: "garden").flatMap(\.notebooks).map(\.uuid), ["nb-garden"])
    }

    func testLargeLibraryIsQuick() {
        let many = (0..<2_500).map { i in
            nb("id-\(i)", "Notebook \(i)", i % 3 == 0 ? [] : ["Folder \(i % 40)", "Sub \(i % 7)"], opened: Double(i))
        }
        measure {
            let index = NotebookIndex(many)
            _ = index.groups(matching: "sub 3")
        }
    }

    // MARK: Sync indicator

    func testSyncIndicator() {
        XCTAssertEqual(NotebookList.syncIndicator(nb("a", "A", pages: 12, synced: 12)), .complete(total: 12))
        XCTAssertEqual(NotebookList.syncIndicator(nb("a", "A", pages: 12, synced: 4)), .partly(synced: 4, total: 12))
        XCTAssertEqual(NotebookList.syncIndicator(nb("a", "A", pages: 12, synced: 0)), .notSynced(total: 12))
        XCTAssertEqual(NotebookList.syncIndicator(nb("a", "A", pages: 0)), .empty)
        XCTAssertEqual(NotebookList.syncIndicator(nb("a", "A", pages: 5, synced: 9)), .complete(total: 5))
    }

    // MARK: Selection

    func testDiffCountsAddedRemovedAndNewPages() {
        let list = [
            nb("a", "A", pages: 12, synced: 12, selected: true),
            nb("b", "B", pages: 21, synced: 0),
            nb("c", "C", pages: 14, synced: 4),
            nb("d", "D", pages: 3, synced: 3, selected: true),
        ]
        let saved = NotebookList.savedSelection(list)
        XCTAssertEqual(saved, ["a", "d"])
        let diff = NotebookList.diff(list, saved: saved, draft: ["a", "b", "c"])
        XCTAssertEqual(diff.added, ["b", "c"])
        XCTAssertEqual(diff.removed, ["d"])
        XCTAssertEqual(diff.newPages, 31)
        XCTAssertFalse(diff.isEmpty)
        XCTAssertFalse(diff.onlyRemoves)

        let removalOnly = NotebookList.diff(list, saved: saved, draft: ["a"])
        XCTAssertTrue(removalOnly.onlyRemoves)
        XCTAssertEqual(removalOnly.newPages, 0)
        XCTAssertTrue(NotebookList.diff(list, saved: saved, draft: saved).isEmpty)
        XCTAssertEqual(NotebookList.orderedSelection(list, draft: ["c", "a"]), ["a", "c"])
    }

    func testSelectAllAndNoneOnlyTouchVisibleRows() {
        let draft: Set<String> = ["hidden-selected", "a"]
        XCTAssertEqual(NotebookList.selectingAll(["a", "b"], in: draft), ["hidden-selected", "a", "b"])
        XCTAssertEqual(NotebookList.selectingNone(["a", "b"], in: draft), ["hidden-selected"])
        XCTAssertEqual(NotebookList.toggling("a", in: draft), ["hidden-selected"])
        XCTAssertEqual(NotebookList.toggling("z", in: draft), ["hidden-selected", "a", "z"])
    }

    func testReconcileDropsVanishedNotebooks() {
        let list = [nb("a", "A"), nb("b", "B")]
        XCTAssertEqual(NotebookList.reconciling(draft: ["a", "gone"], with: list), ["a"])
    }

    // MARK: Allowance

    func testAllowance() {
        let quota = QuotaInfo(used: 188, limit: 200, remaining: 12, resetAt: nil, fetchedAt: nil)
        XCTAssertTrue(NotebookList.exceedsAllowance(pages: 31, quota: quota))
        XCTAssertFalse(NotebookList.exceedsAllowance(pages: 12, quota: quota))
        let unlimited = QuotaInfo(used: 5, limit: -1, remaining: nil, resetAt: nil, fetchedAt: nil)
        XCTAssertFalse(NotebookList.exceedsAllowance(pages: 10_000, quota: unlimited))
        XCTAssertFalse(NotebookList.exceedsAllowance(pages: 10, quota: nil))
        XCTAssertEqual(NotebookList.remainingPages(QuotaInfo(used: 50, limit: 200, remaining: nil, resetAt: nil, fetchedAt: nil)), 150)
        XCTAssertEqual(NotebookList.allowanceUsedFraction(quota)!, 0.94, accuracy: 0.0001)
        XCTAssertNil(NotebookList.allowanceUsedFraction(unlimited))
    }
}
