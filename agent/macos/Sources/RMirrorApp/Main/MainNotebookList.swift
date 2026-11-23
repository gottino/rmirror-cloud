import RMirrorKit
import SwiftUI

/// The core of the window: the view switch, search, list actions and the notebook rows.
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
                    .padding(.top, Theme.Space.m)
                    .padding(.bottom, Theme.Space.s)
                Rectangle().fill(Theme.border).frame(height: 1)
            }
            content
        }
    }

    /// Three lines: title and search; the intro; the view switch with its own actions on the left and
    /// "Select all / Select none" on the right. The view's actions are either "Expand all / Collapse all"
    /// (Folders, not while searching) or "Synced only" (Recent), never both, so the line fits at the
    /// window's narrowest without a menu.
    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: Theme.Space.m) {
                Text(MainCopy.listTitle).font(Theme.Font.heading)
                Spacer(minLength: Theme.Space.m)
                MainSearchField(text: $browser.query, focused: searchFocused)
                    .frame(maxWidth: 260)
            }
            Text(browser.view == .folders ? MainCopy.listIntroFolders : MainCopy.listIntro)
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.m) {
                Picker(MainCopy.viewPickerLabel, selection: Binding(get: { browser.view }, set: { browser.setView($0) })) {
                    Text(MainCopy.viewFolders).tag(NotebookListView.folders)
                    Text(MainCopy.viewRecent).tag(NotebookListView.recent)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
                .accessibilityLabel(MainCopy.viewPickerLabel)
                if browser.view == .folders {
                    if !browser.isSearching {
                        quietLink(MainCopy.expandAll, enabled: browser.canExpandAll) { browser.expandAll() }
                        quietLink(MainCopy.collapseAll, enabled: browser.canCollapseAll) { browser.collapseAll() }
                    }
                } else {
                    MainFilterToggle(title: MainCopy.syncedOnly, help: MainCopy.syncedOnlyHelp, isOn: browser.syncedOnly) {
                        browser.setSyncedOnly(!browser.syncedOnly)
                    }
                }
                Spacer(minLength: Theme.Space.s)
                quietLink(showsShownWording ? MainCopy.selectAllMatching : MainCopy.selectAll,
                          enabled: !browser.allVisibleSelected) { browser.selectAllVisible() }
                quietLink(showsShownWording ? MainCopy.selectNoneMatching : MainCopy.selectNone,
                          enabled: !browser.noVisibleSelected) { browser.selectNoneVisible() }
            }
            .frame(minHeight: 28)
            .fixedSize(horizontal: false, vertical: true)
        }
        .background(
            // Cmd-F focuses the search field.
            Button("") { searchFocused.wrappedValue = true }
                .keyboardShortcut("f", modifiers: .command)
                .opacity(0)
                .accessibilityHidden(true)
        )
    }

    /// "Select all shown" whenever the list shows only some notebooks (a search, or Recent with "Synced only").
    private var showsShownWording: Bool {
        browser.isSearching || (browser.view == .recent && browser.syncedOnly)
    }

    private func quietLink(_ title: String, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .buttonStyle(.rmLink)
            .lineLimit(1)
            .fixedSize()
            .disabled(!enabled)
            .opacity(enabled ? 1 : 0.45)
    }

    @ViewBuilder
    private var content: some View {
        if !loaded && !browser.hasNotebooks {
            MainEmptyState(systemImage: nil, title: MainCopy.loading)
        } else if !browser.hasNotebooks && deleted.isEmpty {
            MainEmptyState(systemImage: "book.closed", title: MainCopy.emptyTitle, message: MainCopy.emptyBody)
        } else {
            MainTreeList(browser: browser, searchFocused: searchFocused, deleted: deleted,
                         resolvingDeleted: resolvingDeleted, onResolveDeleted: onResolveDeleted)
        }
    }
}

/// A small on/off chip with a tick box, for list filters. The box shape and the words carry the state.
struct MainFilterToggle: View {
    let title: String
    let help: String
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: isOn ? "checkmark.square.fill" : "square")
                    .font(.system(size: 13))
                    .foregroundStyle(isOn ? Theme.accent : Theme.textSecondary)
                Text(title)
                    .font(Theme.Font.caption)
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
            }
            .padding(.horizontal, 8)
            .frame(height: 24)
            .background(Capsule().fill(isOn ? Theme.accentTint : Theme.surface))
            .overlay(Capsule().strokeBorder(Theme.border))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .fixedSize()
        .help(help)
        .accessibilityLabel(title)
        .accessibilityValue(isOn ? MainCopy.selected : MainCopy.notSelected)
        .accessibilityAddTraits(isOn ? .isSelected : [])
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
