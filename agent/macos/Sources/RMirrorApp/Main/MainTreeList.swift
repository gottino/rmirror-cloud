import RMirrorKit
import SwiftUI

/// The rows of the notebook list: the folder outline, search results or the Recent list, built lazily
/// so a library of thousands of notebooks stays quick. Owns the keyboard while it has it.
struct MainTreeList: View {
    @ObservedObject var browser: MainBrowserModel
    var searchFocused: FocusState<Bool>.Binding
    let deleted: [DeletedNotebook]
    let resolvingDeleted: Set<String>
    let onResolveDeleted: (String, DeletedNotebookAction) -> Void

    @FocusState private var listFocused: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if !deleted.isEmpty && !browser.isSearching {
                        MainDeletedSection(notebooks: deleted, pageCounts: browser.pageCounts,
                                           resolving: resolvingDeleted, onResolve: onResolveDeleted)
                            .padding(.horizontal, Theme.Space.l)
                            .padding(.vertical, Theme.Space.m)
                    }
                    if browser.rows.isEmpty {
                        if browser.isSearching {
                            MainNoMatches(query: browser.query) { browser.query = "" }
                        } else if browser.view == .recent && browser.syncedOnly {
                            MainNoSynced { browser.setSyncedOnly(false) }
                        }
                    }
                    ForEach(browser.rows) { row in
                        rowView(row)
                    }
                }
                .padding(.bottom, Theme.Space.m)
            }
            .focusable()
            .focused($listFocused)
            .accessibilityLabel(MainCopy.listAccessibilityLabel)
            .onChange(of: browser.highlight) { item in
                guard let item, browser.listHasKeyboard else { return }
                proxy.scrollTo(item)
            }
        }
        .background(MainListKeyCatcher(onKey: handle))
        .onChange(of: listFocused) { focused in
            if focused { browser.listHasKeyboard = true } else if browser.listHasKeyboard { browser.listHasKeyboard = false }
        }
        .onChange(of: searchFocused.wrappedValue) { focused in
            if focused { browser.listHasKeyboard = false }
        }
    }

    @ViewBuilder
    private func rowView(_ row: TreeRow) -> some View {
        let highlighted = browser.listHasKeyboard && browser.highlight == row.item
        switch row.item {
        case .folder(let id):
            if let folder = browser.tree.folders[id] {
                MainFolderRow(folder: folder, isOpen: browser.open.contains(id), tick: browser.tickState(id),
                              selected: browser.selectedCount(id), isHighlighted: highlighted,
                              onToggleOpen: { take(row.item); browser.toggleOpen(id) },
                              onTick: { take(row.item); browser.toggle(row.item) })
            }
        case .notebook(let id):
            if let notebook = browser.tree.notebooks[id] {
                MainNotebookRow(
                    notebook: notebook,
                    depth: row.depth,
                    showsChevronColumn: browser.showsTree,
                    path: browser.showsTree ? nil : browser.tree.pathText(of: id),
                    changed: browser.view == .recent
                        ? RecentList.date(notebook).map { SharedCopy.relative($0, now: browser.now()) } : nil,
                    isSelected: browser.isSelected(id),
                    isSaved: browser.isSaved(id),
                    isHighlighted: highlighted,
                    onToggle: { take(row.item); browser.toggle(row.item) }
                )
            }
        }
    }

    /// A click in the list gives it the keyboard, highlighting the clicked row.
    private func take(_ item: TreeItem) {
        browser.highlight = item
        browser.listHasKeyboard = true
        if searchFocused.wrappedValue { searchFocused.wrappedValue = false }
        listFocused = true
    }

    private func handle(_ key: ListKey, inTextField: Bool) -> Bool {
        if searchFocused.wrappedValue || inTextField {
            // Down from the search field moves into the list; everything else stays with the field.
            guard key == .down, searchFocused.wrappedValue, !browser.rows.isEmpty else { return false }
            searchFocused.wrappedValue = false
            listFocused = true
            browser.enterList()
            return true
        }
        guard browser.listHasKeyboard else { return false }
        browser.handleKey(key)
        return true
    }
}

/// "Synced only" with nothing to show.
struct MainNoSynced: View {
    let onShowAll: () -> Void

    var body: some View {
        VStack(spacing: Theme.Space.s) {
            Text(MainCopy.noSyncedTitle)
                .font(Theme.Font.bodyStrong)
            Text(MainCopy.noSyncedBody)
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
            Button(MainCopy.showAllNotebooks, action: onShowAll)
                .buttonStyle(.rmLink)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Space.xl)
        .padding(.horizontal, Theme.Space.l)
    }
}
