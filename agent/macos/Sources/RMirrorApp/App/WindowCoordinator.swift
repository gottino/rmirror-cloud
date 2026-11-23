import AppKit
import RMirrorKit
import SwiftUI

/// Owns the app's windows and the Dock icon policy.
///
/// rMirror lives in the menu bar. While any of its windows is open (its own, or Sparkle's update
/// window) it also shows a Dock icon and behaves like a normal app (Cmd-Tab, Dock click), so the
/// window is easy to find again. When the last one closes it goes back to menu-bar-only.
@MainActor
final class WindowCoordinator: NSObject, NSWindowDelegate {
    enum WindowKind: String, CaseIterable { case main, settings }

    private var windows: [WindowKind: NSWindow] = [:]
    private let content: (WindowKind) -> AnyView
    private let visibilityChanged: (Bool) -> Void
    private var closeObserver: NSObjectProtocol?

    init(content: @escaping (WindowKind) -> AnyView, visibilityChanged: @escaping (Bool) -> Void = { _ in }) {
        self.content = content
        self.visibilityChanged = visibilityChanged
        super.init()
        // Any window of the app closing (Sparkle's too) may mean none is left.
        closeObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification, object: nil, queue: .main
        ) { [weak self] _ in
            // Decide after the window is actually gone.
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.updatePolicyAfterClose() }
            }
        }
    }

    func show(_ kind: WindowKind) {
        let window = windows[kind] ?? makeWindow(kind)
        windows[kind] = window
        NSApp.setActivationPolicy(.regular)
        if window.isMiniaturized { window.deminiaturize(nil) }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        visibilityChanged(true)
    }

    /// True while any real window of the app is on screen or minimised: rMirror's own, Sparkle's
    /// update window, an open panel. The menu bar item's window, menus and tooltips do not count.
    var hasVisibleWindow: Bool {
        NSApp.windows.contains { window in
            WindowRules.keepsDockIcon(isVisible: window.isVisible, isMiniaturized: window.isMiniaturized,
                                      isTitled: window.styleMask.contains(.titled),
                                      className: String(describing: type(of: window)))
        }
    }

    private func makeWindow(_ kind: WindowKind) -> NSWindow {
        let size: NSSize = kind == .main ? NSSize(width: 760, height: 620) : NSSize(width: 520, height: 460)
        // No `.fullSizeContentView`: the title bar is the standard opaque one, so content starts below it
        // and the header can never sit under the title.
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: kind == .main
                ? [.titled, .closable, .miniaturizable, .resizable]
                : [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = kind == .main ? AppCopy.mainWindowTitle : AppCopy.settingsWindowTitle
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.contentViewController = NSHostingController(rootView: content(kind))
        window.setContentSize(size)
        if kind == .main {
            window.contentMinSize = NSSize(width: 640, height: 520)
            window.setFrameAutosaveName("io.rmirror.agent.main")
        }
        if !window.setFrameUsingName(window.frameAutosaveName) { window.center() }
        return window
    }

    private func updatePolicyAfterClose() {
        guard !hasVisibleWindow, NSApp.activationPolicy() != .accessory else { return }
        NSApp.setActivationPolicy(.accessory)
        visibilityChanged(false)
    }
}
