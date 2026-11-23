import RMirrorKit
import SwiftUI

/// One folder: chevron, tri-state checkbox, icon, name, and "2 of 5 selected" for every notebook below
/// it. Clicking the row opens or closes it; clicking the checkbox ticks or unticks everything below.
/// Folders without notebooks are not shown at all (see `NotebookTree.visibleRows`); the empty state below is a safeguard.
struct MainFolderRow: View {
    let folder: NotebookTree.Folder
    let isOpen: Bool
    let tick: TickState
    let selected: Int
    let isHighlighted: Bool
    let onToggleOpen: () -> Void
    let onTick: () -> Void

    private var isEmpty: Bool { folder.totalNotebooks == 0 }

    var body: some View {
        HStack(spacing: 0) {
            Image(systemName: "chevron.right")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
                .rotationEffect(.degrees(isOpen ? 90 : 0))
                .frame(width: MainRowMetrics.chevron)
                .opacity(folder.hasChildren ? 1 : 0)
                .accessibilityHidden(true)
            Color.clear.frame(width: MainRowMetrics.afterChevron, height: 1)
            if isEmpty {
                Color.clear.frame(width: MainRowMetrics.checkbox, height: MainRowMetrics.checkbox)
            } else {
                Button(action: onTick) { MainCheckbox(state: tick) }
                    .buttonStyle(.plain)
                    .help(tick == .all ? MainCopy.untickFolder : MainCopy.tickFolder)
            }
            Image(systemName: "folder")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: MainRowMetrics.icon)
                .padding(.leading, MainRowMetrics.gap)
                .accessibilityHidden(true)
            Text(folder.name)
                .font(Theme.Font.bodyStrong)
                .foregroundStyle(Theme.text)
                .lineLimit(1)
                .truncationMode(.tail)
                .padding(.leading, MainRowMetrics.gap)
                .layoutPriority(1)
            Spacer(minLength: Theme.Space.s)
            Text(isEmpty ? MainCopy.emptyFolder : MainCopy.folderSummary(selected: selected, total: folder.totalNotebooks))
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
                .fixedSize()
        }
        .opacity(isEmpty ? 0.6 : 1)
        .padding(.leading, MainRowMetrics.leading(depth: folder.depth))
        .padding(.trailing, Theme.Space.l)
        .frame(maxWidth: .infinity, minHeight: MainRowMetrics.height, alignment: .leading)
        .overlay { if isHighlighted { MainRowHighlight() } }
        .overlay(alignment: .bottom) { MainRowSeparator(depth: folder.depth, showsChevronColumn: true) }
        .contentShape(Rectangle())
        .onTapGesture { if folder.hasChildren { onToggleOpen() } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(MainCopy.folderAccessibilityLabel(name: folder.name, selected: selected,
                                                              total: folder.totalNotebooks, expanded: isOpen))
        .accessibilityHint(folder.hasChildren ? MainCopy.folderAccessibilityHint : "")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { if folder.hasChildren { onToggleOpen() } }
        .accessibilityAction(named: Text(tick == .all ? MainCopy.untickFolder : MainCopy.tickFolder)) {
            if !isEmpty { onTick() }
        }
    }
}
