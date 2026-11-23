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
    /// The main window's minimum content size (`WindowCoordinator`).
    private static let mainMinimumSize = CGSize(width: 640, height: 520)
    private static let settingsSize = CGSize(width: 520, height: 460)

    /// True while screens are being rendered: windows then remember nothing and use the fixtures' clock.
    static private(set) var isRendering = false

    static func run(outputDirectory: String) -> Int32 {
        isRendering = true
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
        let library = Fixtures.libraryNotebooks
        func main(_ name: String, core: CoreStatus = .running(CoreConnection(port: 5555, appToken: "preview")),
                  state: AppState?, suggestion: FirstRunSuggestion? = nil,
                  notebooks: [NotebookEntry] = [], guided: Bool = false, waiting: Bool = false,
                  unreachable: Bool = false, deleted: [DeletedNotebook] = [],
                  remarkableRunning: Bool = true) -> Screen {
            Screen(name: name, size: mainSize) {
                // The main window reloads the notebooks and the deleted notebooks from the API when it appears.
                let api = MockLocalAPI(state: state ?? Fixtures.readyState,
                                       notebooks: notebooks.isEmpty ? Fixtures.readyNotebooks : library)
                api.deletedNotebooksResult = .success(deleted)
                let store = AppStore.preview(state: state, core: core, api: api, notebooks: notebooks,
                                             folders: notebooks.isEmpty ? [] : library.folders,
                                             suggestion: suggestion, settings: Fixtures.settings,
                                             guidedSyncActive: guided, isWaitingForSignIn: waiting,
                                             suggestionUnreachable: unreachable, deletedNotebooks: deleted,
                                             remarkableAppRunning: remarkableRunning)
                return AnyView(RootView().environmentObject(store))
            }
        }
        /// The main window on the nested library, with the list set up as given and, with `draft`, an
        /// unsaved change so the footer shows.
        func mainList(_ name: String, size: CGSize? = nil, state: AppState = Fixtures.readyState,
                      library: NotebooksResponse = library, remarkableRunning: Bool = true,
                      list: MainListPreview = MainListPreview(), draft: Set<String>? = nil) -> Screen {
            Screen(name: name, size: size ?? mainSize) {
                let api = MockLocalAPI(state: state, notebooks: library)
                let store = AppStore.preview(state: state, api: api, notebooks: library.notebooks,
                                             folders: library.folders, settings: Fixtures.settings,
                                             remarkableAppRunning: remarkableRunning)
                return AnyView(MainView(previewDraft: draft, previewList: list).environmentObject(store).rmScreen())
            }
        }
        /// The first-sync screen with notebooks ticked (the suggestion is empty when no pages are left).
        func firstSyncTicked(_ name: String, suggestion: FirstRunSuggestion, ticked: Set<String>) -> Screen {
            Screen(name: name, size: mainSize) {
                let entries = Fixtures.threeNotebookSuggestion.notebooks.map {
                    NotebookEntry(uuid: $0.uuid, name: $0.name, pageCount: $0.pageCount)
                }
                let api = MockLocalAPI(state: Fixtures.firstSyncPendingState,
                                       notebooks: NotebooksResponse(folderState: .ok, syncAll: false, notebooks: entries),
                                       suggestion: suggestion)
                var state = Fixtures.firstSyncPendingState
                state.quota = QuotaInfo(used: 200, limit: 200, remaining: 0,
                                        resetAt: Fixtures.now.addingTimeInterval(8 * 86_400), fetchedAt: Fixtures.now)
                let store = AppStore.preview(state: state, api: api, notebooks: entries, suggestion: suggestion,
                                             settings: Fixtures.settings)
                return AnyView(FirstSyncView(previewSelection: ticked).environmentObject(store).rmScreen())
            }
        }
        let caughtUp = Fixtures.catchUpLibraryNotebooks
        let caughtUpSaved = NotebookList.savedSelection(caughtUp.notebooks)
        let caughtUpTicked = caughtUpSaved.union(NotebookList.onServerNotTicked(caughtUp.notebooks, draft: caughtUpSaved))
        var noticeAnswered = Fixtures.readyState
        noticeAnswered.catchUp = CatchUpInfo(state: .done, unselectedOnServer: 0)
        let savedPlusTwo = NotebookList.savedSelection(library.notebooks).union(["nb-roadmap", "nb-ideas"])
        let deepOpen: Set<String> = ["f-work", "f-work-2026", "f-work-2026-clients", "f-work-2026-clients-acme",
                                     "f-work-2025", "f-home", "f-home-finance"]
        let workOpen: Set<String> = ["f-work", "f-work-2026", "f-work-2026-clients", "f-work-2026-clients-acme"]
        var stoppedQuota = Fixtures.quotaExhaustedState
        stoppedQuota.firstSync = FirstSyncInfo(completed: true)
        stoppedQuota.sync = SyncProgress(
            state: .done, outcome: .stoppedQuota,
            counts: SyncCounts(uploaded: 12, failed: 0, leftOutByPageLimit: 0, willRetry: 0,
                               notebooksDone: 1, notebooksTotal: 3, pagesTotal: 23),
            startedAt: Fixtures.now.addingTimeInterval(-300), finishedAt: Fixtures.now.addingTimeInterval(-60))
        var quotaNotPaused = Fixtures.quotaExhaustedState
        quotaNotPaused.queue = QueueInfo(pending: 0, running: true, pausedReason: nil)
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
            firstSyncTicked("first-sync-quota-ticked", suggestion: quotaGone,
                            ticked: Set(Fixtures.threeNotebookSuggestion.notebooks.map(\.uuid))),
            main("first-sync-progress", state: Fixtures.firstSyncRunningState, guided: true),
            main("first-sync-result", state: Fixtures.syncDonePartialState, guided: true),
            main("ready", state: Fixtures.readyState, notebooks: library.notebooks),
            main("ready-quota", state: Fixtures.quotaExhaustedState, notebooks: library.notebooks),
            main("ready-quota-not-paused", state: quotaNotPaused, notebooks: library.notebooks),
            main("ready-deleted", state: Fixtures.readyState, notebooks: library.notebooks,
                 deleted: Fixtures.deletedNotebooks),
            main("starting-catch-up", state: Fixtures.catchingUpState),
            mainList("ready-selection-notice", state: Fixtures.selectionNoticeState, library: caughtUp),
            mainList("ready-selection-notice-and-remarkable", state: Fixtures.selectionNoticeState, library: caughtUp,
                     remarkableRunning: false),
            // After "Tick them": the notice is gone and the footer counts only what is not online yet.
            mainList("ready-selection-notice-ticked", state: noticeAnswered, library: caughtUp, draft: caughtUpTicked),
            main("ready-remarkable-not-running", state: Fixtures.readyState, notebooks: library.notebooks,
                 remarkableRunning: false),
            mainList("ready-footer", draft: savedPlusTwo),
            mainList("ready-quota-footer-min-size", size: mainMinimumSize, state: Fixtures.quotaExhaustedState,
                     draft: savedPlusTwo),
            mainList("tree-nested-open", list: MainListPreview(open: workOpen, highlight: .notebook("nb-kickoff"),
                                                               keyboard: true)),
            mainList("tree-search", list: MainListPreview(query: "2026")),
            mainList("tree-min-size-footer", size: mainMinimumSize,
                     list: MainListPreview(open: deepOpen, highlight: .folder("f-home-finance"), keyboard: true),
                     draft: savedPlusTwo),
            mainList("recent", list: MainListPreview(view: .recent)),
            mainList("recent-synced-only", list: MainListPreview(view: .recent, syncedOnly: true)),
            mainList("recent-synced-only-min-size", size: mainMinimumSize,
                     list: MainListPreview(view: .recent, syncedOnly: true, query: "work")),
            main("first-sync-unreachable", state: Fixtures.firstSyncPendingState, unreachable: true),
            main("first-sync-result-stopped-quota", state: stoppedQuota, guided: true),
            Screen(name: "settings", size: settingsSize) {
                let store = AppStore.preview(state: Fixtures.readyState, settings: Fixtures.settings)
                return AnyView(SettingsView().environmentObject(store))
            },
        ]
    }
}
