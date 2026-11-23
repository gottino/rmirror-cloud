import XCTest
@testable import RMirrorKit

final class WindowRulesTests: XCTestCase {
    func testAnyTitledVisibleOrMinimisedWindowKeepsTheDockIcon() {
        // rMirror's main window minimised while Settings closes.
        XCTAssertTrue(WindowRules.keepsDockIcon(isVisible: false, isMiniaturized: true, isTitled: true, className: "NSWindow"))
        // Sparkle's update window still open after the main window closed.
        XCTAssertTrue(WindowRules.keepsDockIcon(isVisible: true, isMiniaturized: false, isTitled: true, className: "SUUpdateAlertWindow"))
        // The menu bar item's own window, menus, tooltips and closed windows do not.
        XCTAssertFalse(WindowRules.keepsDockIcon(isVisible: true, isMiniaturized: false, isTitled: false, className: "NSStatusBarWindow"))
        XCTAssertFalse(WindowRules.keepsDockIcon(isVisible: true, isMiniaturized: false, isTitled: true, className: "NSStatusBarWindow"))
        XCTAssertFalse(WindowRules.keepsDockIcon(isVisible: true, isMiniaturized: false, isTitled: false, className: "NSMenuWindowManagerWindow"))
        XCTAssertFalse(WindowRules.keepsDockIcon(isVisible: false, isMiniaturized: false, isTitled: true, className: "NSWindow"))
    }

    func testReturnAndEscapeLeaveTheButtonsWhileSearching() {
        XCTAssertFalse(WindowRules.defaultButtonsTakeKeys(searchFieldFocused: true))
        XCTAssertTrue(WindowRules.defaultButtonsTakeKeys(searchFieldFocused: false))
    }

    private func opens(_ stage: Stage, firstLaunch: Bool = false, firstStage: Bool = false, visible: Bool = false) -> Bool {
        WindowRules.opensWindowByItself(stage: stage, firstLaunch: firstLaunch, firstStageThisSession: firstStage,
                                        windowVisible: visible)
    }

    func testExpiredSignInOrFailedCoreDoNotStealFocusWithNoWindowOpen() {
        XCTAssertFalse(opens(.signIn(reason: .expired)))
        XCTAssertFalse(opens(.signIn(reason: .expired), firstStage: true), "a login-item launch with an expired sign-in")
        XCTAssertFalse(opens(.coreProblem(.crashLoop(lastExitCode: 1))))
        // ...but they do on the very first launch, and while a window is already open.
        XCTAssertTrue(opens(.signIn(reason: .signedOut), firstLaunch: true, firstStage: true))
        XCTAssertTrue(opens(.coreProblem(.portInUse), firstLaunch: true, firstStage: true))
        XCTAssertTrue(opens(.signIn(reason: .expired), visible: true))
    }

    func testOnboardingAndReady() {
        XCTAssertTrue(opens(.permission))
        XCTAssertTrue(opens(.firstSync, firstStage: true, visible: true))
        XCTAssertFalse(opens(.firstSync, visible: true))
        XCTAssertTrue(opens(.ready, firstLaunch: true, firstStage: true))
        XCTAssertFalse(opens(.ready, firstStage: true))
        XCTAssertFalse(opens(.starting, firstLaunch: true, firstStage: true))
        XCTAssertFalse(opens(.firstSyncResult, visible: false))
    }
}
