import RMirrorKit
import SwiftUI

/// Appears only while the ticked notebooks differ from the saved choice. Holds the window's one primary button.
struct MainFooter: View {
    let diff: SelectionDiff
    let quota: QuotaInfo?
    let isSaving: Bool
    let isSyncRunning: Bool
    /// False while the search field has focus: Return must not start an upload and Esc must only
    /// clear the search, so the buttons give up their Return / Esc shortcuts meanwhile.
    var takesReturnAndEscape = true
    let onCancel: () -> Void
    let onSave: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.m) {
            VStack(alignment: .leading, spacing: 3) {
                Text(MainCopy.changeSummary(added: diff.added.count, removed: diff.removed.count, pagesToUpload: pages))
                    .font(Theme.Font.bodyStrong)
                    .monospacedDigit()
                if showsAllowanceUse {
                    Text(SharedCopy.allowanceUse(pages: pages, remaining: remaining))
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .monospacedDigit()
                }
                if let remaining, !diff.onlyRemoves, NotebookList.exceedsAllowance(pages: pages, quota: quota) {
                    HStack(alignment: .firstTextBaseline, spacing: 5) {
                        Image(systemName: "exclamationmark.triangle")
                            .accessibilityHidden(true)
                        Text(MainCopy.overAllowance(remaining: remaining))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .font(Theme.Font.caption)
                    .foregroundStyle(Theme.warning)
                }
                if !diff.removed.isEmpty {
                    Text(MainCopy.removalNote)
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if isSyncRunning && !diff.onlyRemoves {
                    Text(MainCopy.waitForSync)
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)

            Button(MainCopy.cancel, action: onCancel)
                .buttonStyle(.rmSecondary)
                .keyboardShortcut(takesReturnAndEscape ? .cancelAction : nil)
                .disabled(isSaving)
            Button(action: onSave) {
                HStack(spacing: 6) {
                    if isSaving { ProgressView().controlSize(.small).tint(Theme.textOnAccent) }
                    Text(isSaving ? MainCopy.saving : (diff.onlyRemoves ? MainCopy.save : MainCopy.saveAndSync))
                }
            }
            .buttonStyle(.rmPrimary)
            .keyboardShortcut(takesReturnAndEscape ? .defaultAction : nil)
            .disabled(isSaving || (isSyncRunning && !diff.onlyRemoves))
        }
        .padding(.horizontal, Theme.Space.l)
        .padding(.vertical, Theme.Space.m)
        .background(Theme.surface)
        .overlay(alignment: .top) { Rectangle().fill(Theme.border).frame(height: 1) }
    }

    private var remaining: Int? { NotebookList.remainingPages(quota) }
    /// What "Save and sync" uploads: every ticked notebook's pages not uploaded yet. Nothing for a
    /// change that only unticks (that is saved without a sync).
    private var pages: Int { diff.onlyRemoves ? 0 : diff.pagesToUpload }
    /// "Uses 31 of your 196 remaining pages", unless it is more than what is left: then the warning says it instead.
    private var showsAllowanceUse: Bool {
        pages > 0 && remaining != nil && !NotebookList.exceedsAllowance(pages: pages, quota: quota)
    }
}
