import RMirrorKit
import SwiftUI

/// One notebook with a checkbox: name, folder (if any) and page count.
struct OnboardingNotebookRow: View {
    let name: String
    let folder: String?
    let pages: Int
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Space.m) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(name)
                        .font(Theme.Font.bodyStrong)
                        .foregroundStyle(Theme.text)
                        .lineLimit(2)
                    if let folder, !folder.isEmpty {
                        Text(folder)
                            .font(Theme.Font.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                Spacer(minLength: Theme.Space.m)
                Text(SharedCopy.pages(pages))
                    .font(Theme.Font.body)
                    .foregroundStyle(Theme.textSecondary)
                    .monospacedDigit()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .toggleStyle(.checkbox)
        .padding(.vertical, Theme.Space.s)
        .padding(.horizontal, Theme.Space.m)
        .accessibilityLabel(OnboardingCopy.notebookRow(name: name, folder: folder, pages: pages))
    }
}

/// The suggested notebooks: a short list, all visible.
struct OnboardingSuggestedList: View {
    let notebooks: [SuggestedNotebook]
    let isOn: (String) -> Binding<Bool>

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(notebooks.enumerated()), id: \.element.id) { index, notebook in
                if index > 0 { Divider().overlay(Theme.border) }
                OnboardingNotebookRow(name: notebook.name, folder: nil, pages: notebook.pageCount,
                                      isOn: isOn(notebook.uuid))
            }
        }
        .rmCard(padding: Theme.Space.xs)
    }
}

/// Every notebook, searchable by name and folder, in a scrolling box.
struct OnboardingAllNotebooksList: View {
    let notebooks: [NotebookEntry]
    @Binding var query: String
    var searchFocused: FocusState<Bool>.Binding
    let isOn: (String) -> Binding<Bool>

    static let listHeight: CGFloat = 230

    private var filtered: [NotebookEntry] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return notebooks }
        return notebooks.filter {
            $0.name.localizedCaseInsensitiveContains(trimmed)
                || folderText($0).localizedCaseInsensitiveContains(trimmed)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) {
            TextField(OnboardingCopy.searchPrompt, text: $query)
                .textFieldStyle(.roundedBorder)
                .font(Theme.Font.body)
                .accessibilityLabel(OnboardingCopy.searchPrompt)
                .focused(searchFocused)
                .onExitCommand { query = "" }

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(Array(filtered.enumerated()), id: \.element.id) { index, notebook in
                        if index > 0 { Divider().overlay(Theme.border) }
                        OnboardingNotebookRow(name: notebook.name, folder: folderText(notebook),
                                              pages: notebook.pageCount, isOn: isOn(notebook.uuid))
                    }
                    if filtered.isEmpty {
                        Text(OnboardingCopy.noMatches(query.trimmingCharacters(in: .whitespacesAndNewlines)))
                            .font(Theme.Font.body)
                            .foregroundStyle(Theme.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(Theme.Space.m)
                    }
                }
                .padding(Theme.Space.xs)
            }
            .frame(height: Self.listHeight)
            .background(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous).fill(Theme.surface))
            .overlay(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous).strokeBorder(Theme.border))
            .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous))
        }
    }

    private func folderText(_ notebook: NotebookEntry) -> String {
        notebook.folderPath.joined(separator: " / ")
    }
}
