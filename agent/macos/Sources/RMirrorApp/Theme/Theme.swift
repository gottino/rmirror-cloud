import AppKit
import SwiftUI

/// rMirror's palette and shared controls. Every screen uses these; no view sets raw colours.
///
/// The light values are the product palette with the two contrast corrections from the
/// November 2026 UX review (gray #6b6661, terracotta #b24a44) so body text and buttons meet
/// WCAG AA. Each colour has a dark-mode partner chosen for the same contrast.
enum Theme {
    // Surfaces
    static let background = Color(light: 0xFAF8F5, dark: 0x1E1D1B)
    static let surface = Color(light: 0xFFFFFF, dark: 0x282724)
    static let surfaceSunken = Color(light: 0xF2EEE6, dark: 0x232220)
    static let border = Color(light: 0xE4DED3, dark: 0x3B3934)

    // Text
    static let text = Color(light: 0x2C2C2C, dark: 0xEDEAE3)
    static let textSecondary = Color(light: 0x6B6661, dark: 0xA9A49A)
    static let textOnAccent = Color(light: 0xFFFFFF, dark: 0x1E1D1B)

    // Brand and meaning. Accent is for the one main action on a screen.
    static let accent = Color(light: 0xB24A44, dark: 0xE58F88)
    static let accentPressed = Color(light: 0x983E39, dark: 0xD67B74)
    static let accentTint = Color(light: 0xF6E5E3, dark: 0x3B2826)
    static let success = Color(light: 0x3F6F52, dark: 0x9BC7A8)
    static let successTint = Color(light: 0xE3EEE6, dark: 0x25352A)
    static let warning = Color(light: 0x7A5A0C, dark: 0xE8C46B)
    static let warningTint = Color(light: 0xF8ECC8, dark: 0x3A3118)
    static let danger = Color(light: 0xA1382F, dark: 0xEF9D95)

    enum Space {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 12
        static let l: CGFloat = 20
        static let xl: CGFloat = 32
    }

    static let cornerRadius: CGFloat = 10

    enum Font {
        static let title = SwiftUI.Font.system(size: 24, weight: .semibold)
        static let heading = SwiftUI.Font.system(size: 17, weight: .semibold)
        static let body = SwiftUI.Font.system(size: 14)
        static let bodyStrong = SwiftUI.Font.system(size: 14, weight: .medium)
        static let caption = SwiftUI.Font.system(size: 12)
        static let label = SwiftUI.Font.system(size: 11, weight: .semibold)
    }
}

extension Color {
    /// A colour that follows the system appearance.
    init(light: UInt32, dark: UInt32) {
        self.init(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return NSColor(hex: isDark ? dark : light)
        })
    }
}

extension NSColor {
    convenience init(hex: UInt32) {
        self.init(
            srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

// MARK: - Buttons

/// The single main action on a screen.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Font.bodyStrong)
            .foregroundStyle(Theme.textOnAccent)
            .padding(.horizontal, 18)
            .padding(.vertical, 9)
            .frame(minHeight: 34)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(configuration.isPressed ? Theme.accentPressed : Theme.accent)
            )
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(Rectangle())
    }
}

/// Any other action.
struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Font.bodyStrong)
            .foregroundStyle(Theme.text)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .frame(minHeight: 32)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(configuration.isPressed ? Theme.surfaceSunken : Theme.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Theme.border)
            )
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(Rectangle())
    }
}

/// A text-only action, for quiet alternatives such as "Choose different notebooks".
struct LinkButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Font.body)
            .foregroundStyle(Theme.accent)
            .underline(configuration.isPressed)
            .contentShape(Rectangle())
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var rmPrimary: PrimaryButtonStyle { PrimaryButtonStyle() }
}

extension ButtonStyle where Self == SecondaryButtonStyle {
    static var rmSecondary: SecondaryButtonStyle { SecondaryButtonStyle() }
}

extension ButtonStyle where Self == LinkButtonStyle {
    static var rmLink: LinkButtonStyle { LinkButtonStyle() }
}

// MARK: - Shared pieces

extension View {
    /// A bordered panel. Use for a group that is one object, not for every block.
    func rmCard(padding: CGFloat = Theme.Space.l) -> some View {
        self
            .padding(padding)
            .background(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous).fill(Theme.surface))
            .overlay(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous).strokeBorder(Theme.border))
    }

    /// Window background for every top-level screen.
    func rmScreen() -> some View {
        self
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.background)
            .foregroundStyle(Theme.text)
    }
}

/// A small state label: a coloured dot plus words, so state never relies on colour alone.
struct StatusPill: View {
    enum Tone { case good, attention, problem, neutral }

    let text: String
    let tone: Tone

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(foreground).frame(width: 7, height: 7)
            Text(text).font(Theme.Font.caption.weight(.medium)).foregroundStyle(foreground)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(Capsule().fill(background))
        .accessibilityElement(children: .combine)
    }

    private var foreground: Color {
        switch tone {
        case .good: return Theme.success
        case .attention: return Theme.warning
        case .problem: return Theme.danger
        case .neutral: return Theme.textSecondary
        }
    }

    private var background: Color {
        switch tone {
        case .good: return Theme.successTint
        case .attention: return Theme.warningTint
        case .problem: return Theme.accentTint
        case .neutral: return Theme.surfaceSunken
        }
    }
}
