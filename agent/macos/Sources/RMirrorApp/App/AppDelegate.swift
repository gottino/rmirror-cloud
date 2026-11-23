import AppKit
import Combine
import RMirrorKit
import SwiftUI

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var supervisor: CoreSupervisor?
    private var store: AppStore!
    private var windows: WindowCoordinator!
    private var statusItem: StatusItemController!
    private var cancellables: Set<AnyCancellable> = []
    private var hasShownWindowForFirstRun = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        store = AppStore(dependencies: .init(
            makeAPI: { LocalAPIClient(port: $0.port, appToken: $0.appToken) },
            openURL: { NSWorkspace.shared.open($0) },
            restartCore: { [weak self] in self?.supervisor?.restart() }
        ))

        windows = WindowCoordinator(
            content: { [store] kind in
                switch kind {
                case .main: return AnyView(RootView().environmentObject(store!))
                case .settings: return AnyView(SettingsView().environmentObject(store!))
                }
            },
            visibilityChanged: { [store] visible in store!.setWindowVisible(visible) }
        )

        statusItem = StatusItemController(
            store: store,
            openMain: { [weak self] in self?.windows.show(.main) },
            openSettings: { [weak self] in self?.windows.show(.settings) },
            checkForUpdates: { [weak self] in self?.checkForUpdates() }
        )

        startCore()

        // Bring the window forward by itself whenever the user has something to do:
        // first launch, sign-in, a missing permission, the first sync.
        store.$stage
            .removeDuplicates()
            .receive(on: RunLoop.main)
            .sink { [weak self] stage in self?.stageChanged(stage) }
            .store(in: &cancellables)

        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleURLEvent(_:withReply:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
    }

    private func startCore() {
        guard let spec = CoreLocator.launchSpec() else {
            store.coreStatusChanged(.failed(.cannotLaunch("core not found in the app bundle")))
            return
        }
        let supervisor = CoreSupervisor(spec: spec)
        supervisor.setStatusHandler { [weak self] status in
            Task { @MainActor in self?.store.coreStatusChanged(status) }
        }
        self.supervisor = supervisor
        supervisor.start()
    }

    private func stageChanged(_ stage: Stage) {
        switch stage {
        case .starting, .ready:
            // Nothing for the user to do. Show the window once on the very first launch only.
            if case .ready = stage, !hasShownWindowForFirstRun, !Preferences.hasLaunchedBefore {
                windows.show(.main)
            }
        case .firstSyncProgress, .firstSyncResult:
            break
        case .coreProblem, .signIn, .remarkableMissing, .permission, .firstSync:
            if !hasShownWindowForFirstRun || !windows.hasVisibleWindow {
                windows.show(.main)
            }
        }
        if stage != .starting {
            hasShownWindowForFirstRun = true
            Preferences.hasLaunchedBefore = true
        }
    }

    /// `rmirror://…` links, used by the sign-in result page to bring the app forward.
    /// The link carries nothing the app trusts; it only opens the window.
    @objc private func handleURLEvent(_ event: NSAppleEventDescriptor, withReply reply: NSAppleEventDescriptor) {
        windows.show(.main)
        Task { await store.refresh() }
    }

    /// Clicking the Dock icon or opening the app again shows the window.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        windows.show(.main)
        return false
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationWillTerminate(_ notification: Notification) {
        supervisor?.stopAndWait()
    }

    private func checkForUpdates() {
        Updater.shared.checkForUpdates(store: store, showWindow: { [weak self] in self?.windows.show(.main) })
    }
}

enum Preferences {
    private static let launchedKey = "hasLaunchedBefore"
    static var hasLaunchedBefore: Bool {
        get { UserDefaults.standard.bool(forKey: launchedKey) }
        set { UserDefaults.standard.set(newValue, forKey: launchedKey) }
    }
}
