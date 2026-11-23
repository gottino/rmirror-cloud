import RMirrorKit
import SwiftUI

/// The core of the window: search, select all/none, and the grouped notebook rows.
/// Rows are built lazily, so a library of thousands of notebooks stays quick.
struct MainNotebookSection: View {
    @ObservedObject var browser: MainBrowserModel
    /// Owned by `MainView`, which also hands it to the footer (see `WindowRules.defaultButtonsTakeKeys`).
    var searchFocused: FocusState<Bool>.Binding
    let loaded: Bool
    let deleted: [DeletedNotebook]
    let resolvingDeleted: Set<String>
    let onResolveDeleted: (String, DeletedNotebookAction) -> Void

    var body: some View {
        VStack(spacing: 0) {
            if browser.hasNotebooks {
                toolbar
                    .padding(.horizontal, Theme.Space.l)
                    .padding(.vertical, Theme.Space.m)
                Rectangle().fill(Theme.border).frame(height: 1)
            }
            content
        }
    }

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: Theme.Space.m) {
                Text(MainCopy.listTitle).font(Theme.Font.heading)
                Spacer(minLength: Theme.Space.m)
                MainSearchField(text: $browser.query, focused: searchFocused)
                    .frame(maxWidth: 260)
            }
            HStack(spacing: Theme.Space.m) {
                Text(MainCopy.listIntro)
                    .font(Theme.Font.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: Theme.Space.m)
                Button(browser.isSearching ? MainCopy.selectAllMatching : MainCopy.selectAll) { browser.selectAllVisible() }
                    .buttonStyle(.rmLink)
                    .disabled(browser.allVisibleSelected)
                    .opacity(browser.allVisibleSelected ? 0.45 : 1)
                Button(browser.isSearching ? MainCopy.selectNoneMatching : MainCopy.selectNone) { browser.selectNoneVisible() }
                    .buttonStyle(.rmLink)
                    .disabled(browser.noVisibleSelected)
                    .opacity(browser.noVisibleSelected ? 0.45 : 1)
            }
            .fixedSize(horizontal: false, vertical: true)
            .font(Theme.Font.caption)
        }
        .background(
            // Cmd-F focuses the search field.
            Button("") { searchFocused.wrappedValue = true }
                .keyboardShortcut("f", modifiers: .command)
                .opacity(0)
                .accessibilityHidden(true)
        )
    }

    @ViewBuilder
    private var content: some View {
        if !loaded && !browser.hasNotebooks {
            MainEmptyState(systemImage: nil, title: MainCopy.loading)
        } else if !browser.hasNotebooks && deleted.isEmpty {
            MainEmptyState(systemImage: "book.closed", title: MainCopy.emptyTitle, message: MainCopy.emptyBody)
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                    if !deleted.isEmpty && !browser.isSearching {
                        MainDeletedSection(notebooks: deleted, pageCounts: browser.pageCounts,
                                           resolving: resolvingDeleted, onResolve: onResolveDeleted)
                            .padding(.horizontal, Theme.Space.l)
                            .padding(.vertical, Theme.Space.m)
                    }
                    if browser.groups.isEmpty && browser.isSearching {
                        MainNoMatches(query: browser.query) { browser.query = "" }
                    }
                    ForEach(browser.groups) { group in
                        Section {
                            ForEach(group.notebooks) { notebook in
                                MainNotebookRow(
                                    notebook: notebook,
                                    isSelected: browser.isSelected(notebook.uuid),
                                    isSaved: browser.isSaved(notebook.uuid),
                                    onToggle: { browser.toggle(notebook.uuid) }
                                )
                            }
                        } header: {
                            MainGroupHeader(title: group.folder ?? MainCopy.topLevelGroup, count: group.notebooks.count)
                        }
                    }
                }
                .padding(.bottom, Theme.Space.m)
            }
        }
    }
}

struct MainSearchField: View {
    @Binding var text: String
    var focused: FocusState<Bool>.Binding

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .accessibilityHidden(true)
            TextField(MainCopy.searchPlaceholder, text: $text)
                .textFieldStyle(.plain)
                .font(Theme.Font.body)
                .focused(focused)
                // Esc clears the search; the footer's Cancel gives up Esc while this field has focus.
                .onExitCommand { text = "" }
            if !text.isEmpty {
                Button {
                    text = ""
                } label: {
                    Image(systemName: "xmark.circle.fill").font(.system(size: 12))
                }
                .buttonStyle(MainIconButtonStyle())
                .help(MainCopy.clearSearch)
                .accessibilityLabel(MainCopy.clearSearch)
            }
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(Theme.surface))
        .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(Theme.border))
    }
}

/// Pinned heading for one folder. Opaque so rows scroll underneath it cleanly.
struct MainGroupHeader: View {
    let title: String
    let count: Int

    var body: some View {
        HStack(spacing: Theme.Space.s) {
            Text(title)
                .font(Theme.Font.label)
                .foregroundStyle(Theme.text)
                .lineLimit(1)
            Text(SharedCopy.notebooks(count))
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
            Spacer()
        }
        .padding(.horizontal, Theme.Space.l)
        .padding(.top, Theme.Space.m)
        .padding(.bottom, 6)
        .background(Theme.background)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(MainCopy.groupAccessibility(folder: title, count: count))
        .accessibilityAddTraits(.isHeader)
    }
}

/// One notebook: checkbox, name, sub-folder, sync state and page count. The whole row toggles.
struct MainNotebookRow: View {
    let notebook: NotebookEntry
    let isSelected: Bool
    let isSaved: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: Theme.Space.m) {
                Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                    .font(.system(size: 15))
                    .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(notebook.name)
                        .font(Theme.Font.body)
                        .foregroundStyle(Theme.text)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    if let subfolder {
                        Text(subfolder)
                            .font(Theme.Font.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                .layoutPriority(1)
                Spacer(minLength: Theme.Space.s)
                if showsIndicator {
                    MainSyncIndicatorLabel(indicator: indicator)
                }
                Text(SharedCopy.pages(notebook.pageCount))
                    .font(Theme.Font.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .monospacedDigit()
                    .frame(minWidth: 64, alignment: .trailing)
            }
            .padding(.horizontal, Theme.Space.l)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(isSelected ? Theme.accentTint.opacity(0.5) : Color.clear)
            .overlay(alignment: .bottom) {
                Rectangle().fill(Theme.border.opacity(0.7)).frame(height: 0.5).padding(.leading, Theme.Space.l + 30)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(MainRowButtonStyle())
        .accessibilityLabel(MainCopy.rowAccessibilityLabel(name: notebook.name, pages: notebook.pageCount, selected: isSelected))
        .accessibilityValue(MainCopy.rowAccessibilityValue(folder: notebook.folderPath.isEmpty ? nil : notebook.folderPath.joined(separator: " / "),
                                                           indicator: MainCopy.syncIndicator(indicator)))
        .accessibilityHint(MainCopy.rowAccessibilityHint)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private var subfolder: String? { NotebookList.subfolderPath(notebook) }
    private var indicator: SyncIndicator { NotebookList.syncIndicator(notebook) }

    /// "Not synced yet" on every unticked notebook would be noise in a long list, so the sync state is
    /// shown for notebooks that are (or are about to be) synced, and for any that already have pages in rMirror.
    private var showsIndicator: Bool { isSelected || isSaved || notebook.syncedPages > 0 }
}

struct MainSyncIndicatorLabel: View {
    let indicator: SyncIndicator

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: symbol)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(symbolColor)
                .accessibilityHidden(true)
            Text(MainCopy.syncIndicator(indicator))
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
                .lineLimit(1)
        }
    }

    private var symbol: String {
        switch indicator {
        case .complete: return "checkmark.circle.fill"
        case .partly: return "circle.lefthalf.filled"
        case .notSynced, .empty: return "circle.dashed"
        }
    }

    private var symbolColor: Color {
        if case .complete = indicator { return Theme.success }
        return Theme.textSecondary
    }
}

struct MainRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? Theme.surfaceSunken : Color.clear)
    }
}

/// Centred message for the loading and "no notebooks" states.
struct MainEmptyState: View {
    let systemImage: String?
    let title: String
    var message: String?

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.system(size: 28, weight: .light))
                    .foregroundStyle(Theme.textSecondary)
                    .accessibilityHidden(true)
            } else {
                ProgressView().controlSize(.small)
            }
            Text(title).font(Theme.Font.heading)
            if let message {
                Text(message)
                    .font(Theme.Font.body)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 380)
            }
        }
        .padding(Theme.Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}

struct MainNoMatches: View {
    let query: String
    let onClear: () -> Void

    var body: some View {
        VStack(spacing: Theme.Space.s) {
            Text(MainCopy.noMatches(query.trimmingCharacters(in: .whitespaces)))
                .font(Theme.Font.bodyStrong)
                .multilineTextAlignment(.center)
            Text(MainCopy.noMatchesBody)
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
            Button(MainCopy.clearSearch, action: onClear)
                .buttonStyle(.rmLink)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Space.xl)
        .padding(.horizontal, Theme.Space.l)
    }
}
