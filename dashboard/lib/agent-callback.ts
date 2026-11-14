const ALLOWED_HOSTNAMES = ['localhost', '127.0.0.1'];
const CALLBACK_PATH = '/auth/callback';

/**
 * Parse and validate the agent's local callback URL.
 * Returns the parsed URL when it is plain http on a loopback host, carries no
 * credentials and points at the agent's callback path; otherwise null.
 * Any port is allowed.
 */
export function parseCallbackUrl(url: string): URL | null {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:') return null;
    if (!ALLOWED_HOSTNAMES.includes(parsed.hostname)) return null;
    if (parsed.username || parsed.password) return null;
    if (parsed.pathname !== CALLBACK_PATH) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function validateCallbackUrl(url: string): boolean {
  return parseCallbackUrl(url) !== null;
}

/** Build the redirect to the agent with the token set as a query parameter. */
export function buildAgentRedirectUrl(callbackUrl: string, token: string): string | null {
  const parsed = parseCallbackUrl(callbackUrl);
  if (!parsed) return null;
  parsed.searchParams.set('token', token);
  return parsed.toString();
}
