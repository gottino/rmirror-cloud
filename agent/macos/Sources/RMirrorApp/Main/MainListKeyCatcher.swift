import AppKit
import RMirrorKit
import SwiftUI

/// Sees key presses in its own window before the window handles them, so the notebook list can take
/// the arrow keys, Space and Return on macOS 13 (where SwiftUI has no `onKeyPress`). The handler
/// returns true for a key it used; that key then goes nowhere else. Keys typed into a text field
/// (the search field's editor has the keyboard) are never offered.
struct MainListKeyCatcher: NSViewRepresentable {
    /// Gets the key and whether the search field's editor has the keyboard.
    let onKey: (ListKey, _ inTextField: Bool) -> Bool

    func makeCoordinator() -> Coordinator { Coordinator(onKey: onKey) }

    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        context.coordinator.view = view
        context.coordinator.install()
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.onKey = onKey
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.uninstall()
    }

    static func listKey(_ event: NSEvent) -> ListKey? {
        // Shortcuts with Command, Option, Control or Shift are someone else's.
        guard event.modifierFlags.intersection([.command, .option, .control, .shift]).isEmpty else { return nil }
        switch event.keyCode {
        case 126: return .up
        case 125: return .down
        case 123: return .left
        case 124: return .right
        case 49: return .space
        case 36, 76: return .enter
        default: return nil
        }
    }

    final class Coordinator {
        var onKey: (ListKey, Bool) -> Bool
        weak var view: NSView?
        private var monitor: Any?

        init(onKey: @escaping (ListKey, Bool) -> Bool) { self.onKey = onKey }

        func install() {
            guard monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                guard let self, let window = self.view?.window, event.window === window, window.isKeyWindow,
                      let key = MainListKeyCatcher.listKey(event) else { return event }
                let inTextField = window.firstResponder is NSText
                return self.onKey(key, inTextField) ? nil : event
            }
        }

        func uninstall() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }

        deinit { uninstall() }
    }
}
