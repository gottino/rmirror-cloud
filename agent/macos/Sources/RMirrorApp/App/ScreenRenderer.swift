import AppKit
import RMirrorKit
import SwiftUI

/// Developer aid: renders every screen from fixture data, in light and dark, to PNG files.
///
/// Each view is hosted in an `NSHostingView` inside an offscreen borderless window (never shown)
/// and captured with `cacheDisplay`. `ImageRenderer` does not draw AppKit-backed controls
/// (toggles, text fields, progress bars, lists) faithfully, so it is not used here.
@MainActor
enum ScreenRenderer {
    private struct Screen {
        let name: String
        let size: CGSize
        let make: () -> AnyView
    }

    private static let mainSize = CGSize(width: 760, height: 620)
    private static let settingsSize = CGSize(width: 520, height: 460)

    static func run(outputDirectory: String) -> Int32 {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)

        let directory = URL(fileURLWithPath: outputDirectory, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            print("Cannot create \(outputDirectory): \(error.localizedDescription)")
            return 1
        }

        var failures = 0
        for (index, screen) in screens().enumerated() {
            for dark in [false, true] {
                let file = String(format: "%02d-%@-%@.png", index + 1, screen.name, dark ? "dark" : "light")
                let url = directory.appendingPathComponent(file)
                if let data = render(screen, dark: dark) {
                    do {
                        try data.write(to: url)
                        print("wrote \(url.path)")
                    } catch {
                        print("FAILED \(file): \(error.localizedDescription)")
                        failures += 1
                    }
                } else {
                    print("FAILED \(file): could not render")
                    failures += 1
                }
            }
        }
        return failures == 0 ? 0 : 1
    }

    // MARK: Rendering

    private static func render(_ screen: Screen, dark: Bool) -> Data? {
        let appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        let content = screen.make()
            .environment(\.colorScheme, dark ? .dark : .light)
            .frame(width: screen.size.width, height: screen.size.height)

        let host = NSHostingView(rootView: content)
        let frame = NSRect(origin: .zero, size: screen.size)
        host.frame = frame
        host.appearance = appearance

        let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.appearance = appearance
        window.isReleasedWhenClosed = false
        window.contentView = host

        // Let SwiftUI lay out and any `.task` loads finish before capturing.
        settle(host, window: window)

        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(screen.size.width * 2), pixelsHigh: Int(screen.size.height * 2),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
        rep.size = screen.size
        var ok = false
        appearance.map { appearance in
            appearance.performAsCurrentDrawingAppearance {
                host.cacheDisplay(in: host.bounds, to: rep)
                ok = true
            }
        }
        window.close()
        guard ok, !isBlank(rep) else { return nil }
        return rep.representation(using: .png, properties: [:])
    }

    private static func settle(_ host: NSHostingView<some View>, window: NSWindow) {
        for _ in 0..<6 {
            host.layoutSubtreeIfNeeded()
            host.displayIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.1))
        }
    }

    /// A capture that is a single flat colour means nothing was drawn.
    private static func isBlank(_ rep: NSBitmapImageRep) -> Bool {
        guard let first = rep.colorAt(x: 0, y: 0) else { return true }
        let w = rep.pixelsWide, h = rep.pixelsHigh
        for (x, y) in [(w / 2, h / 2), (w / 3, h / 3), (w * 2 / 3, h * 2 / 3), (w / 2, h / 4), (w / 4, h / 2)] {
            if let c = rep.colorAt(x: x, y: y), c != first { return false }
        }
        // Sparse screens can be mostly flat; scan every 7th row for any difference.
        for y in stride(from: 0, to: h, by: 7) {
            for x in stride(from: 0, to: w, by: 5) {
                if let c = rep.colorAt(x: x, y: y), c != first { return false }
            }
        }
        return true
    }

    // MARK: Screens

    private static func screens() -> [Screen] {
        func main(_ name: String, core: CoreStatus = .running(CoreConnection(port: 5555, appToken: "preview")),
                  state: AppState?, suggestion: FirstRunSuggestion? = nil,
                  notebooks: [NotebookEntry] = [], guided: Bool = false, waiting: Bool = false) -> Screen {
            Screen(name: name, size: mainSize) {
                let store = AppStore.preview(state: state, core: core, notebooks: notebooks,
                                             suggestion: suggestion, settings: Fixtures.settings,
                                             guidedSyncActive: guided, isWaitingForSignIn: waiting)
                return AnyView(RootView().environmentObject(store))
            }
        }
        let quotaGone = FirstRunSuggestion(
            notebooks: [], totalPages: 0,
            quota: SuggestionQuota(limit: 200, remaining: 0), reason: .quotaExhausted)

        return [
            main("starting", core: .starting, state: nil),
            main("core-port-in-use", core: .failed(.portInUse), state: nil),
            main("core-crash-loop", core: .failed(.crashLoop(lastExitCode: 1)), state: nil),
            main("sign-in", state: Fixtures.signedOutState),
            main("sign-in-waiting", state: Fixtures.signedOutState, waiting: true),
            main("sign-in-expired", state: Fixtures.signInRequiredState),
            main("remarkable-missing", state: Fixtures.folderMissingState),
            main("permission", state: Fixtures.folderUnreadableState),
            main("first-sync", state: Fixtures.firstSyncPendingState, suggestion: Fixtures.threeNotebookSuggestion),
            main("first-sync-quota", state: Fixtures.firstSyncPendingState, suggestion: quotaGone),
            main("first-sync-progress", state: Fixtures.firstSyncRunningState, guided: true),
            main("first-sync-result", state: Fixtures.syncDonePartialState, guided: true),
            main("ready", state: Fixtures.readyState, notebooks: Fixtures.readyNotebooks.notebooks),
            main("ready-quota", state: Fixtures.quotaExhaustedState, notebooks: Fixtures.readyNotebooks.notebooks),
            Screen(name: "settings", size: settingsSize) {
                let store = AppStore.preview(state: Fixtures.readyState, settings: Fixtures.settings)
                return AnyView(SettingsView().environmentObject(store))
            },
        ]
    }
}
