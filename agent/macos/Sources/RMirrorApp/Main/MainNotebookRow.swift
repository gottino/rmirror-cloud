import RMirrorKit
import SwiftUI

/// Shared column widths so chevrons, checkboxes and icons line up across levels and row kinds.
enum MainRowMetrics {
    /// Extra leading space per folder level.
    static let indent: CGFloat = 22
    static let chevron: CGFloat = 14
    static let afterChevron: CGFloat = 6
    static let checkbox: CGFloat = 18
    static let icon: CGFloat = 18
    static let gap: CGFloat = 8
    static let height: CGFloat = 40
    /// Height of a row with a second line (folder path in search results and Recent).
    static let tallHeight: CGFloat = 46

    static func leading(depth: Int) -> CGFloat { Theme.Space.l + CGFloat(depth) * indent }
}

/// One notebook: checkbox, icon, name (with its folder path in flat lists), sync state, page count and,
/// in Recent, when it last changed. The whole row toggles the tick.
struct MainNotebookRow: View {
    let notebook: NotebookEntry
    let depth: Int
    /// In the outline, an empty chevron column keeps the checkbox under the folders' checkboxes.
    let showsChevronColumn: Bool
    /// "Work › 2026" in search results and Recent; nil in the outline and at the top level.
    let path: String?
    /// "3 days ago" in Recent.
    let changed: String?
    let isSelected: Bool
    let isSaved: Bool
    let isHighlighted: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 0) {
                if showsChevronColumn {
                    Color.clear.frame(width: MainRowMetrics.chevron + MainRowMetrics.afterChevron, height: 1)
                }
                MainCheckbox(state: isSelected ? .all : .none)
                Image(systemName: notebook.documentType == "notebook" ? "book.closed" : "doc.text")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: MainRowMetrics.icon)
                    .padding(.leading, MainRowMetrics.gap)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 1) {
                    Text(notebook.name)
                        .font(Theme.Font.body)
                        .foregroundStyle(Theme.text)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    if let path {
                        Text(path)
                            .font(Theme.Font.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                .padding(.leading, MainRowMetrics.gap)
                .layoutPriority(1)
                Spacer(minLength: Theme.Space.s)
                HStack(spacing: Theme.Space.m) {
                    if showsIndicator {
                        MainSyncIndicatorLabel(indicator: indicator)
                    }
                    Text(SharedCopy.pages(notebook.pageCount))
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .monospacedDigit()
                        .frame(minWidth: 56, alignment: .trailing)
                    if let changed {
                        Text(changed)
                            .font(Theme.Font.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .frame(minWidth: 88, alignment: .trailing)
                    }
                }
                .fixedSize()
            }
            .padding(.leading, MainRowMetrics.leading(depth: depth))
            .padding(.trailing, Theme.Space.l)
            .frame(maxWidth: .infinity, minHeight: path == nil ? MainRowMetrics.height : MainRowMetrics.tallHeight,
                   alignment: .leading)
            .background(isSelected ? Theme.accentTint.opacity(0.5) : Color.clear)
            .overlay { if isHighlighted { MainRowHighlight() } }
            .overlay(alignment: .bottom) { MainRowSeparator(depth: depth, showsChevronColumn: showsChevronColumn) }
            .contentShape(Rectangle())
        }
        .buttonStyle(MainRowButtonStyle())
        .accessibilityLabel(MainCopy.rowAccessibilityLabel(name: notebook.name, pages: notebook.pageCount, selected: isSelected))
        .accessibilityValue(accessibilityValue)
        .accessibilityHint(MainCopy.rowAccessibilityHint)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private var accessibilityValue: String {
        let value = MainCopy.rowAccessibilityValue(folder: notebook.folderPath.isEmpty ? nil : notebook.folderPath.joined(separator: " / "),
                                                   indicator: MainCopy.syncIndicator(indicator))
        guard let changed else { return value }
        return value + ". " + MainCopy.changedAccessibility(changed)
    }

    private var indicator: SyncIndicator { NotebookList.syncIndicator(notebook) }

    /// "Not synced yet" on every unticked notebook would be noise in a long list, so the sync state is
    /// shown for notebooks that are (or are about to be) synced, and for any that already have pages in rMirror.
    private var showsIndicator: Bool { isSelected || isSaved || notebook.syncedPages > 0 }
}

/// A tick box: empty, a dash (some notebooks below a folder ticked), or a tick. The shape differs for
/// each state, so it never relies on colour alone.
struct MainCheckbox: View {
    let state: TickState

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 15))
            .foregroundStyle(state == .none ? Theme.textSecondary : Theme.accent)
            .frame(width: MainRowMetrics.checkbox, height: MainRowMetrics.checkbox)
            .accessibilityHidden(true)
    }

    private var symbol: String {
        switch state {
        case .none: return "square"
        case .mixed: return "minus.square.fill"
        case .all: return "checkmark.square.fill"
        }
    }
}

/// The keyboard highlight: an outline, so it reads on ticked (tinted) rows too.
struct MainRowHighlight: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
            .strokeBorder(Theme.accent, lineWidth: 2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .accessibilityHidden(true)
    }
}

struct MainRowSeparator: View {
    let depth: Int
    let showsChevronColumn: Bool

    var body: some View {
        let chevron = showsChevronColumn ? MainRowMetrics.chevron + MainRowMetrics.afterChevron : 0
        Rectangle()
            .fill(Theme.border.opacity(0.7))
            .frame(height: 0.5)
            .padding(.leading, MainRowMetrics.leading(depth: depth) + chevron + MainRowMetrics.checkbox + MainRowMetrics.gap)
    }
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
