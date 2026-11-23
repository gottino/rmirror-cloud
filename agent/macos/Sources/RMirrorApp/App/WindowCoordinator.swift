import AppKit
import SwiftUI

/// Owns the app's windows and the Dock icon policy.
///
/// rMirror lives in the menu bar. While one of its windows is open it also shows a Dock icon
/// and behaves like a normal app (Cmd-Tab, Dock click), so the window is easy to find again.
/// When the last window closes it goes back to menu-bar-only.
@MainActor
final class WindowCoordinator: NSObject, NSWindowDelegate {
    enum WindowKind: String, CaseIterable { case main, settings }

    private var windows: [WindowKind: NSWindow] = [:]
    private let content: (WindowKind) -> AnyView
    private let visibilityChanged: (Bool) -> Void

    init(content: @escaping (WindowKind) -> AnyView, visibilityChanged: @escaping (Bool) -> Void = { _ in }) {
        self.content = content
        self.visibilityChanged = visibilityChanged
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

    var hasVisibleWindow: Bool { windows.values.contains { $0.isVisible } }

    private func makeWindow(_ kind: WindowKind) -> NSWindow {
        let size: NSSize = kind == .main ? NSSize(width: 760, height: 620) : NSSize(width: 520, height: 460)
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: kind == .main
                ? [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
                : [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = kind == .main ? "rMirror" : "rMirror Settings"
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

    func windowWillClose(_ notification: Notification) {
        // Decide after this window is actually gone.
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.hasVisibleWindow else { return }
            NSApp.setActivationPolicy(.accessory)
            self.visibilityChanged(false)
        }
    }
}
