import Foundation

/// A string enumeration that never fails to decode: values this app does not know become `.unknown(raw)`.
public protocol CodedString: RawRepresentable, Codable, Hashable, Sendable where RawValue == String {}

extension CodedString {
    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        guard let value = Self(rawValue: raw) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "unmappable \(raw)"))
        }
        self = value
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

public enum FolderState: CodedString {
    case ok, missing, unreadable
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "ok": self = .ok
        case "missing": self = .missing
        case "unreadable": self = .unreadable
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .ok: return "ok"
        case .missing: return "missing"
        case .unreadable: return "unreadable"
        case .unknown(let s): return s
        }
    }
}

public enum WatcherState: CodedString {
    case idle, starting, running
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "idle": self = .idle
        case "starting": self = .starting
        case "running": self = .running
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .idle: return "idle"
        case .starting: return "starting"
        case .running: return "running"
        case .unknown(let s): return s
        }
    }
}

public enum PausedReason: CodedString {
    case signIn, quota, rateLimited, offline
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "sign_in": self = .signIn
        case "quota": self = .quota
        case "rate_limited": self = .rateLimited
        case "offline": self = .offline
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .signIn: return "sign_in"
        case .quota: return "quota"
        case .rateLimited: return "rate_limited"
        case .offline: return "offline"
        case .unknown(let s): return s
        }
    }
}

public enum SyncState: CodedString {
    case idle, running, done
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "idle": self = .idle
        case "running": self = .running
        case "done": self = .done
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .idle: return "idle"
        case .running: return "running"
        case .done: return "done"
        case .unknown(let s): return s
        }
    }
}

public enum SyncOutcome: CodedString {
    case success, partial, stoppedQuota, stoppedSignIn, failed
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "success": self = .success
        case "partial": self = .partial
        case "stopped_quota": self = .stoppedQuota
        case "stopped_sign_in": self = .stoppedSignIn
        case "failed": self = .failed
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .success: return "success"
        case .partial: return "partial"
        case .stoppedQuota: return "stopped_quota"
        case .stoppedSignIn: return "stopped_sign_in"
        case .failed: return "failed"
        case .unknown(let s): return s
        }
    }
}

public enum EnvironmentName: CodedString {
    case production, staging, custom
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "production": self = .production
        case "staging": self = .staging
        case "custom": self = .custom
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .production: return "production"
        case .staging: return "staging"
        case .custom: return "custom"
        case .unknown(let s): return s
        }
    }
}

/// Where the stored sign-in stands.
public enum AuthState: CodedString {
    /// A stored sign-in exists and is being checked with the cloud.
    case checking
    case signedIn
    case signedOut
    /// A stored sign-in exists but the cloud cannot be reached; the core keeps retrying.
    case offline
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "checking": self = .checking
        case "signed_in": self = .signedIn
        case "signed_out": self = .signedOut
        case "offline": self = .offline
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .checking: return "checking"
        case .signedIn: return "signed_in"
        case .signedOut: return "signed_out"
        case .offline: return "offline"
        case .unknown(let s): return s
        }
    }
}

public enum SuggestionReason: CodedString {
    case ok, noNotebooks, quotaExhausted, notSignedIn, folderUnavailable
    /// There are notebooks, but none is small enough for the pages left this month.
    case noneFit
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "ok": self = .ok
        case "no_notebooks": self = .noNotebooks
        case "quota_exhausted": self = .quotaExhausted
        case "not_signed_in": self = .notSignedIn
        case "folder_unavailable": self = .folderUnavailable
        case "none_fit": self = .noneFit
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .ok: return "ok"
        case .noNotebooks: return "no_notebooks"
        case .quotaExhausted: return "quota_exhausted"
        case .notSignedIn: return "not_signed_in"
        case .folderUnavailable: return "folder_unavailable"
        case .noneFit: return "none_fit"
        case .unknown(let s): return s
        }
    }
}

public enum LocalAPIErrorCode: CodedString {
    case badAppToken, notSignedIn, invalidRequest, syncAlreadyRunning
    case coreNotReady, cloudTimeout, cloudError, internalError
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "bad_app_token": self = .badAppToken
        case "not_signed_in": self = .notSignedIn
        case "invalid_request": self = .invalidRequest
        case "sync_already_running": self = .syncAlreadyRunning
        case "core_not_ready": self = .coreNotReady
        case "cloud_timeout": self = .cloudTimeout
        case "cloud_error": self = .cloudError
        case "internal": self = .internalError
        default: self = .unknown(rawValue)
        }
    }

    public var rawValue: String {
        switch self {
        case .badAppToken: return "bad_app_token"
        case .notSignedIn: return "not_signed_in"
        case .invalidRequest: return "invalid_request"
        case .syncAlreadyRunning: return "sync_already_running"
        case .coreNotReady: return "core_not_ready"
        case .cloudTimeout: return "cloud_timeout"
        case .cloudError: return "cloud_error"
        case .internalError: return "internal"
        case .unknown(let s): return s
        }
    }
}

/// Whether the core has asked the current server what it already has (`catch_up.state`).
/// A value this app does not know reads as `notNeeded`, so it never holds the app on the starting screen.
public enum CatchUpState: String, Codable, Hashable, Sendable {
    /// The core is asking the server (or retrying); the app shows its starting screen.
    case pending
    case done
    /// The server is too old to answer; the selection uploads and the server skips what it has.
    case unavailable
    /// Set up by an earlier version; nothing to ask.
    case notNeeded = "not_needed"

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = CatchUpState(rawValue: raw) ?? .notNeeded
    }
}

/// Action for a notebook that was deleted on the server.
public enum DeletedNotebookAction: String, Codable, Hashable, Sendable {
    case resync
    case dismiss
}
