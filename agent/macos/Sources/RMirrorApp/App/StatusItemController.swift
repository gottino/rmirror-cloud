import AppKit
import Combine
import RMirrorKit

/// The menu bar item: a status line and four commands (five while an update is waiting).
/// No item duplicates another.
@MainActor
final class StatusItemController: NSObject {
    private let item: NSStatusItem
    private let statusLine = NSMenuItem(title: SharedCopy.statusLine(stage: .starting, state: nil), action: nil, keyEquivalent: "")
    private var updateItem: NSMenuItem!
    private var needsAttention = false
    private var updateAvailable = false
    private let openMain: () -> Void
    private let openSettings: () -> Void
    private let checkForUpdates: () -> Void
    private var cancellables: Set<AnyCancellable> = []

    @MainActor
    init(store: AppStore, openMain: @escaping () -> Void, openSettings: @escaping () -> Void, checkForUpdates: @escaping () -> Void) {
        self.openMain = openMain
        self.openSettings = openSettings
        self.checkForUpdates = checkForUpdates
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        super.init()

        if let button = item.button {
            button.image = StatusItemController.icon()
            button.setAccessibilityLabel(AppCopy.appName)
        }

        let menu = NSMenu()
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        menu.addItem(command(AppCopy.StatusMenu.open, #selector(openMainAction), key: "o"))
        menu.addItem(command(AppCopy.StatusMenu.settings, #selector(openSettingsAction), key: ","))
        // A background check found an update: the reminder rMirror controls (see `Updater`).
        updateItem = command(AppCopy.StatusMenu.updateAvailable, #selector(checkForUpdatesAction))
        updateItem.isHidden = true
        menu.addItem(updateItem)
        menu.addItem(command(AppCopy.StatusMenu.checkForUpdates, #selector(checkForUpdatesAction)))
        menu.addItem(.separator())
        menu.addItem(command(AppCopy.StatusMenu.quit, #selector(quitAction), key: "q"))
        item.menu = menu

        store.$stage.combineLatest(store.$state)
            .receive(on: RunLoop.main)
            .sink { [weak self] stage, state in
                self?.update(stage: stage, state: state)
            }
            .store(in: &cancellables)
    }

    private func command(_ title: String, _ action: Selector, key: String = "") -> NSMenuItem {
        let menuItem = NSMenuItem(title: title, action: action, keyEquivalent: key)
        menuItem.target = self
        return menuItem
    }

    /// Shows or hides "Update Available…" (and the dot on the icon).
    func setUpdateAvailable(_ available: Bool) {
        updateAvailable = available
        updateItem.isHidden = !available
        refreshIcon()
    }

    private func update(stage: Stage, state: AppState?) {
        let line = SharedCopy.statusLine(stage: stage, state: state)
        statusLine.title = line
        item.button?.toolTip = AppCopy.StatusMenu.tooltip(line)
        // A small dot on the icon when the user has something to do. With no window open this is
        // the only signal for an expired sign-in or a core that cannot run (the window does not
        // open by itself for those).
        switch stage {
        case .coreProblem, .signIn, .remarkableMissing, .permission, .firstSync: needsAttention = true
        default: needsAttention = state?.queue.pausedReason == .signIn
        }
        refreshIcon()
    }

    private func refreshIcon() {
        item.button?.image = StatusItemController.icon(attention: needsAttention || updateAvailable)
    }

    /// The rM logo, as a template image so it follows the menu bar's light or dark appearance.
    /// With `attention`, a small dot sits on its top-right corner.
    static func icon(attention: Bool = false) -> NSImage {
        guard let logo = logoImage else { return drawnIcon(attention: attention) }
        // The artwork is 48 x 44 px; shown at 22 x 20 pt it stays sharp on Retina displays.
        let size = NSSize(width: 22, height: 20)
        let image = NSImage(size: size, flipped: false) { rect in
            logo.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1)
            if attention {
                NSColor.black.setFill()
                NSBezierPath(ovalIn: NSRect(x: rect.maxX - 6, y: rect.maxY - 6, width: 6, height: 6)).fill()
            }
            return true
        }
        image.isTemplate = true
        return image
    }

    /// `MenuBarIcon.png` from the app bundle (the build script copies `agent/resources/menubar_icon.png`
    /// there). When running from the build folder during development, the file is read from the repo.
    private static let logoImage: NSImage? = {
        if let url = Bundle.main.url(forResource: "MenuBarIcon", withExtension: "png"),
           let image = NSImage(contentsOf: url) {
            return image
        }
        #if DEBUG
        var folder = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { folder.deleteLastPathComponent() }   // …/agent
        let source = folder.appendingPathComponent("resources/menubar_icon.png")
        if let image = NSImage(contentsOf: source) { return image }
        #endif
        return nil
    }()

    /// Fallback when the logo file is missing: a small page with written lines.
    private static func drawnIcon(attention: Bool) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size, flipped: false) { _ in
            NSColor.black.setStroke()
            NSColor.black.setFill()
            let page = NSBezierPath(roundedRect: NSRect(x: 3.5, y: 2, width: 11, height: 14), xRadius: 2, yRadius: 2)
            page.lineWidth = 1.4
            page.stroke()
            for (y, end) in [(11.5, 12.0), (8.5, 12.0), (5.5, 9.5)] as [(CGFloat, CGFloat)] {
                let line = NSBezierPath()
                line.move(to: NSPoint(x: 6, y: y))
                line.line(to: NSPoint(x: end, y: y))
                line.lineWidth = 1.3
                line.lineCapStyle = .round
                line.stroke()
            }
            if attention {
                NSBezierPath(ovalIn: NSRect(x: 12, y: 12, width: 6, height: 6)).fill()
            }
            return true
        }
        image.isTemplate = true
        return image
    }

    @objc private func openMainAction() { openMain() }
    @objc private func openSettingsAction() { openSettings() }
    @objc private func checkForUpdatesAction() { checkForUpdates() }
    @objc private func quitAction() { NSApp.terminate(nil) }
}
