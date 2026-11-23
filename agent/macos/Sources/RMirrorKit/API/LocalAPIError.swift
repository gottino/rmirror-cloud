import Foundation

/// Errors from the local API client. No user-facing strings: the app owns all wording.
public enum LocalAPIError: Error, Equatable, Sendable {
    /// Connection refused, timeout or any transport failure talking to the core on localhost.
    case coreUnreachable
    /// The core answered with a non-2xx status and (usually) the contract's error body.
    case api(code: LocalAPIErrorCode, status: Int, detail: String?)
    /// A 2xx response whose body could not be decoded. The string is a technical description for logs.
    case decoding(String)
}
