import Foundation

/// The one rule for web addresses the app opens in the browser or accepts as a server:
/// `https` anywhere, plain `http` only to this Mac (`127.0.0.1`, `localhost`, `::1`).
/// Anything else (`file:`, custom schemes, plain http to another host) is refused.
///
/// System URLs the app builds itself as constants (`x-apple.systempreferences:…`) do not go
/// through here; they are never taken from the core or the network.
public enum SafeURL {
    public static let loopbackHosts: Set<String> = ["127.0.0.1", "localhost", "::1"]

    /// The URL to hand to the browser, or nil if it must not be opened.
    public static func browserURL(from string: String?) -> URL? {
        guard let string else { return nil }
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: trimmed) else { return nil }
        return browserURL(url)
    }

    public static func browserURL(_ url: URL) -> URL? {
        guard let scheme = url.scheme?.lowercased(), let host = normalizedHost(url) else { return nil }
        switch scheme {
        case "https": return url
        case "http": return loopbackHosts.contains(host) ? url : nil
        default: return nil
        }
    }

    /// Whether `text` may be used as a custom server address (the core enforces the same rule).
    public static func isAllowedServerURL(_ text: String) -> Bool {
        browserURL(from: text) != nil
    }

    /// The website's notebook list for the core's `environment.dashboard_url`:
    /// "https://rmirror.io/" → "https://rmirror.io/dashboard". Nil when missing or not allowed.
    public static func dashboardURL(base: String?) -> URL? {
        guard var base = base?.trimmingCharacters(in: .whitespacesAndNewlines), !base.isEmpty else { return nil }
        while base.hasSuffix("/") { base.removeLast() }
        return browserURL(from: base + "/dashboard")
    }

    /// Lower-cased host without IPv6 brackets, or nil when there is none.
    static func normalizedHost(_ url: URL) -> String? {
        guard var host = url.host?.lowercased(), !host.isEmpty else { return nil }
        if host.hasPrefix("["), host.hasSuffix("]") { host = String(host.dropFirst().dropLast()) }
        return host.isEmpty ? nil : host
    }
}
