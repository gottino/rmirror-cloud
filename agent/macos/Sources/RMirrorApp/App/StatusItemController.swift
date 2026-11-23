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
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
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

    /// A template image so it follows the menu bar's light or dark appearance.
    static func icon(attention: Bool = false) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size, flipped: false) { rect in
            NSColor.black.setStroke()
            NSColor.black.setFill()
            // A page with two written lines, mirrored: the reMarkable page going to the cloud.
            let page = NSBezierPath(roundedRect: NSRect(x: 3.5, y: 2, width: 11, height: 14), xRadius: 2, yRadius: 2)
            page.lineWidth = 1.4
            page.stroke()
            for y in [11.5, 8.5] as [CGFloat] {
                let line = NSBezierPath()
                line.move(to: NSPoint(x: 6, y: y))
                line.line(to: NSPoint(x: 12, y: y))
                line.lineWidth = 1.3
                line.lineCapStyle = .round
                line.stroke()
            }
            let short = NSBezierPath()
            short.move(to: NSPoint(x: 6, y: 5.5))
            short.line(to: NSPoint(x: 9.5, y: 5.5))
            short.lineWidth = 1.3
            short.lineCapStyle = .round
            short.stroke()
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
