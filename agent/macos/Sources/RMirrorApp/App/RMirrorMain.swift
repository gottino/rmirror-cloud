import AppKit

@main
@MainActor
enum RMirrorMain {
    // Keeps the delegate alive for the life of the app (NSApplication holds it weakly).
    private static var delegate: AppDelegate?

    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        RMirrorMain.delegate = delegate
        app.delegate = delegate
        app.run()
    }
}
