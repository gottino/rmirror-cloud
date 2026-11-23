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

public enum SuggestionReason: CodedString {
    case ok, noNotebooks, quotaExhausted, notSignedIn, folderUnavailable
    case unknown(String)

    public init(rawValue: String) {
        switch rawValue {
        case "ok": self = .ok
        case "no_notebooks": self = .noNotebooks
        case "quota_exhausted": self = .quotaExhausted
        case "not_signed_in": self = .notSignedIn
        case "folder_unavailable": self = .folderUnavailable
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

/// Action for a notebook that was deleted on the server.
public enum DeletedNotebookAction: String, Codable, Hashable, Sendable {
    case resync
    case dismiss
}
