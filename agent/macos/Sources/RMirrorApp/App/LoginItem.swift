import Foundation
import ServiceManagement

/// "Open rMirror when I log in", backed by the system login-item service.
enum LoginItem {
    static var isEnabled: Bool { SMAppService.mainApp.status == .enabled }

    /// The user turned it off in System Settings; only they can turn it back on there.
    static var needsApprovalInSystemSettings: Bool { SMAppService.mainApp.status == .requiresApproval }

    @discardableResult
    static func setEnabled(_ enabled: Bool) -> Bool {
        do {
            if enabled {
                if SMAppService.mainApp.status != .enabled { try SMAppService.mainApp.register() }
            } else if SMAppService.mainApp.status == .enabled {
                try SMAppService.mainApp.unregister()
            }
            return true
        } catch {
            NSLog("rMirror: login item change failed: \(error.localizedDescription)")
            return false
        }
    }

    static func openSystemSettings() { SMAppService.openSystemSettingsLoginItems() }
}
