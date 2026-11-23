import AppKit
import Combine
import RMirrorKit

/// The menu bar item: a status line and four commands. No item duplicates another.
@MainActor
final class StatusItemController: NSObject {
    private let item: NSStatusItem
    private let statusLine = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
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
            button.setAccessibilityLabel("rMirror")
        }

        let menu = NSMenu()
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        menu.addItem(command("Open rMirror", #selector(openMainAction), key: "o"))
        menu.addItem(command("Settings…", #selector(openSettingsAction), key: ","))
        menu.addItem(command("Check for Updates…", #selector(checkForUpdatesAction)))
        menu.addItem(.separator())
        menu.addItem(command("Quit rMirror", #selector(quitAction), key: "q"))
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

    private func update(stage: Stage, state: AppState?) {
        let line = SharedCopy.statusLine(stage: stage, state: state)
        statusLine.title = line
        item.button?.toolTip = "rMirror: \(line)"
        // A small dot on the icon when the user has something to do.
        let needsAttention: Bool
        switch stage {
        case .coreProblem, .signIn, .remarkableMissing, .permission, .firstSync: needsAttention = true
        default: needsAttention = state?.queue.pausedReason == .signIn
        }
        item.button?.image = StatusItemController.icon(attention: needsAttention)
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
