import RMirrorKit
import SwiftUI

/// Notebooks the user deleted on the website. Each one needs a decision: upload it again, or leave it out.
struct MainDeletedSection: View {
    let notebooks: [DeletedNotebook]
    /// Page counts of notebooks the core still lists, by identifier. A notebook removed on the web is
    /// usually not among them; then "Sync again" says it uploads the whole notebook.
    let pageCounts: [String: Int]
    let resolving: Set<String>
    let onResolve: (String, DeletedNotebookAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.s) {
                Image(systemName: "trash")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.textSecondary)
                    .accessibilityHidden(true)
                Text(MainCopy.deletedTitle).font(Theme.Font.bodyStrong)
                    .accessibilityAddTraits(.isHeader)
            }
            Text(MainCopy.deletedBody)
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(notebooks) { notebook in
                HStack(spacing: Theme.Space.m) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(notebook.name).font(Theme.Font.body).lineLimit(1)
                        if let deletedAt = notebook.deletedAt {
                            Text(MainCopy.deletedWhen(SharedCopy.relative(deletedAt)))
                                .font(Theme.Font.caption)
                                .foregroundStyle(Theme.textSecondary)
                        }
                        Text(MainCopy.syncAgainUploads(pages: pageCounts[notebook.uuid]))
                            .font(Theme.Font.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .monospacedDigit()
                    }
                    .accessibilityElement(children: .combine)
                    Spacer(minLength: Theme.Space.m)
                    Button(MainCopy.keepRemoved) { onResolve(notebook.uuid, .dismiss) }
                        .buttonStyle(.rmSecondary)
                    Button(MainCopy.syncAgain) { onResolve(notebook.uuid, .resync) }
                        .buttonStyle(.rmSecondary)
                }
                .disabled(resolving.contains(notebook.uuid))
                .padding(.top, 4)
            }
        }
        .rmCard(padding: Theme.Space.m)
    }
}
