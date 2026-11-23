import AppKit
import RMirrorKit

/// The app's main menu. rMirror has no nib and no SwiftUI `App`, so without this Cmd-Q, Cmd-W,
/// Cmd-comma and the text editing commands (copy, paste, select all, undo) would do nothing while a
/// window is open. The menu bar shows it only while rMirror is a regular app (a window is open);
/// its shortcuts work whenever rMirror is the active app.
@MainActor
enum MainMenu {
    /// Keeps the target of "Settings…" alive for the life of the menu.
    private static var target: MenuTarget?

    static func install(openSettings: @escaping () -> Void) {
        let target = MenuTarget(openSettings: openSettings)
        Self.target = target
        let copy = AppCopy.MainMenu.self

        let mainMenu = NSMenu()

        // App menu (its title is replaced by the app's name by macOS).
        let appMenu = NSMenu(title: AppCopy.appName)
        appMenu.addItem(withTitle: copy.about,
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        let settings = appMenu.addItem(withTitle: copy.settings, action: #selector(MenuTarget.openSettings(_:)),
                                       keyEquivalent: ",")
        settings.target = target
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: copy.hide, action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = appMenu.addItem(withTitle: copy.hideOthers,
                                         action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(withTitle: copy.showAll, action: #selector(NSApplication.unhideAllApplications(_:)),
                        keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: copy.quit, action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        mainMenu.addItem(submenuItem(appMenu))

        // Edit: standard responder-chain selectors, so text fields get them for free.
        let editMenu = NSMenu(title: copy.edit)
        editMenu.addItem(withTitle: copy.undo, action: Selector(("undo:")), keyEquivalent: "z")
        let redo = editMenu.addItem(withTitle: copy.redo, action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: copy.cut, action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: copy.copy, action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: copy.paste, action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: copy.selectAll, action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        mainMenu.addItem(submenuItem(editMenu))

        // Window.
        let windowMenu = NSMenu(title: copy.window)
        windowMenu.addItem(withTitle: copy.minimise, action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: copy.close, action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowMenu.addItem(.separator())
        windowMenu.addItem(withTitle: copy.bringAllToFront, action: #selector(NSApplication.arrangeInFront(_:)),
                           keyEquivalent: "")
        mainMenu.addItem(submenuItem(windowMenu))

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = windowMenu
    }

    private static func submenuItem(_ menu: NSMenu) -> NSMenuItem {
        let item = NSMenuItem(title: menu.title, action: nil, keyEquivalent: "")
        item.submenu = menu
        return item
    }
}

@MainActor
private final class MenuTarget: NSObject {
    private let open: () -> Void
    init(openSettings: @escaping () -> Void) { open = openSettings }
    @objc func openSettings(_ sender: Any?) { open() }
}
