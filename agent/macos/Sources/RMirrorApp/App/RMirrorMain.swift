import AppKit

@main
@MainActor
enum RMirrorMain {
    // Keeps the delegate alive for the life of the app (NSApplication holds it weakly).
    private static var delegate: AppDelegate?

    static func main() {
        // Developer aid: `RMirrorApp --render-screens <directory>` writes a PNG of every screen
        // from fixture data, in light and dark, then exits. Used for review and documentation.
        let arguments = CommandLine.arguments
        if let flag = arguments.firstIndex(of: "--render-screens") {
            let directory = arguments.count > flag + 1 ? arguments[flag + 1] : "screens"
            exit(ScreenRenderer.run(outputDirectory: directory))
        }
        let app = NSApplication.shared
        let delegate = AppDelegate()
        RMirrorMain.delegate = delegate
        app.delegate = delegate
        app.run()
    }
}
