import RMirrorKit
import SwiftUI

/// An inline message strip: an icon, a short title, a few lines, optional actions and an optional dismiss.
struct MainNotice<Actions: View>: View {
    enum Kind { case info, attention, problem }

    let kind: Kind
    let systemImage: String
    var title: String?
    var lines: [String] = []
    var onDismiss: (() -> Void)?
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Space.m) {
            Image(systemName: systemImage)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(iconColor)
                .padding(.top, 1)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                if let title {
                    Text(title).font(Theme.Font.bodyStrong)
                }
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(title == nil ? Theme.Font.body : Theme.Font.caption)
                        .foregroundStyle(title == nil ? Theme.text : Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            actions()
            if let onDismiss {
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(MainIconButtonStyle())
                .help(MainCopy.dismiss)
                .accessibilityLabel(MainCopy.dismiss)
            }
        }
        .padding(.horizontal, Theme.Space.m)
        .padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(background))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Theme.border.opacity(kind == .info ? 1 : 0)))
    }

    private var background: Color {
        switch kind {
        case .info: return Theme.surface
        case .attention: return Theme.warningTint
        case .problem: return Theme.accentTint
        }
    }

    private var iconColor: Color {
        switch kind {
        case .info: return Theme.textSecondary
        case .attention: return Theme.warning
        case .problem: return Theme.danger
        }
    }
}

extension MainNotice where Actions == EmptyView {
    init(kind: Kind, systemImage: String, title: String? = nil, lines: [String] = [], onDismiss: (() -> Void)? = nil) {
        self.init(kind: kind, systemImage: systemImage, title: title, lines: lines, onDismiss: onDismiss) { EmptyView() }
    }
}

/// Inline progress while a sync runs.
struct MainSyncProgressStrip: View {
    let counts: SyncCounts

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(MainCopy.syncingTitle).font(Theme.Font.bodyStrong)
                Spacer()
                if let notebook = SharedCopy.notebookProgressLine(counts) {
                    Text(notebook).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary).monospacedDigit()
                }
            }
            if let fraction = SharedCopy.progressFraction(counts) {
                ProgressView(value: fraction).progressViewStyle(.linear).tint(Theme.accent)
            } else {
                ProgressView().progressViewStyle(.linear).tint(Theme.accent)
            }
            Text(SharedCopy.progressLine(counts))
                .font(Theme.Font.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
        }
        .padding(.horizontal, Theme.Space.m)
        .padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Theme.surface))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Theme.border))
        .accessibilityElement(children: .combine)
    }
}
