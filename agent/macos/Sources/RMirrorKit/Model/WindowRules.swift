import Foundation

/// Small window-management decisions, kept free of AppKit so they can be tested.
public enum WindowRules {
    /// Whether a window keeps rMirror a regular app with a Dock icon. Any titled window of the app
    /// counts while it is on screen or minimised (rMirror's own windows, Sparkle's update window,
    /// an open panel); the menu bar item's own window and untitled helper windows (menus, tooltips) do not.
    public static func keepsDockIcon(isVisible: Bool, isMiniaturized: Bool, isTitled: Bool, className: String) -> Bool {
        guard isVisible || isMiniaturized, isTitled else { return false }
        return !className.contains("StatusBar")
    }

    /// Return and Esc go to the window's default and cancel buttons only while no search field has
    /// keyboard focus. In a search field, Return must not start an upload and Esc must only clear the search.
    public static func defaultButtonsTakeKeys(searchFieldFocused: Bool) -> Bool {
        !searchFieldFocused
    }

    /// Whether reaching `stage` brings the main window forward by itself.
    ///
    /// - Parameters:
    ///   - firstLaunch: rMirror has never got past starting on this Mac before.
    ///   - firstStageThisSession: this is the first stage after starting, in this run of the app.
    ///   - windowVisible: one of rMirror's windows is open.
    ///
    /// Sign-in expiring or the sync part failing can happen at any time, for example at night: with no
    /// window open the menu bar icon shows a dot instead of the window stealing focus. Onboarding
    /// stages open the window when nothing is showing, as the user is setting rMirror up.
    public static func opensWindowByItself(stage: Stage, firstLaunch: Bool, firstStageThisSession: Bool,
                                           windowVisible: Bool) -> Bool {
        switch stage {
        case .starting, .firstSyncProgress, .firstSyncResult:
            return false
        case .ready:
            return firstLaunch
        case .coreProblem, .signIn:
            return firstLaunch || windowVisible
        case .remarkableMissing, .permission, .firstSync:
            return firstStageThisSession || !windowVisible
        }
    }
}
