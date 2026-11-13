// Security headers for the dashboard, applied by headers() in next.config.js.
//
// CommonJS on purpose: next.config.js requires this at build time. headers()
// is evaluated during `next build`, so every env var read here (including
// CSP_ENFORCE) is a build-time setting, also for the standalone deploy build.
//
// Scripts use 'unsafe-inline' rather than a nonce: a nonce would need the
// middleware to set the CSP per request and every page to render dynamically.
// The named hosts below still limit where scripts and requests can go.

const DEFAULT_API_URL = 'https://rmirror.io/api/v1'; // same fallback as lib/apiClient.ts

const CLERK_DEV_INSTANCES = 'https://*.clerk.accounts.dev';
const CLERK_IMAGES = 'https://img.clerk.com';
// Clerk's SDK reports usage events here for development instances (pk_test_ keys).
const CLERK_TELEMETRY = 'https://clerk-telemetry.com';
const CLOUDFLARE_CHALLENGES = 'https://challenges.cloudflare.com'; // Clerk bot protection

const HSTS = 'max-age=31536000; includeSubDomains';

/** Origin ("https://host[:port]") of a URL, or null if it is not an http(s) URL. */
function originOf(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

/**
 * Clerk frontend API host encoded in a publishable key
 * ("pk_test_" or "pk_live_" + base64("<host>$")), or null.
 */
function clerkFrontendApiFromKey(publishableKey) {
  const match = /^pk_(test|live)_([A-Za-z0-9+/=_-]+)$/.exec(publishableKey || '');
  if (!match) return null;
  let decoded;
  try {
    decoded = Buffer.from(match[2], 'base64').toString('utf8');
  } catch {
    return null;
  }
  const host = decoded.endsWith('$') ? decoded.slice(0, -1) : decoded;
  return /^[a-z0-9.-]+$/i.test(host) && host.includes('.') ? host.toLowerCase() : null;
}

/**
 * Build the Content-Security-Policy string.
 * @param {{ apiUrl?: string, umamiUrl?: string, clerkPublishableKey?: string, isDev?: boolean }} options
 */
function buildContentSecurityPolicy({ apiUrl, umamiUrl, clerkPublishableKey, isDev = false }) {
  const apiOrigin = originOf(apiUrl) || originOf(DEFAULT_API_URL);
  const umamiOrigin = originOf(umamiUrl);

  const clerkHost = clerkFrontendApiFromKey(clerkPublishableKey);
  const clerkOrigins = clerkHost ? [`https://${clerkHost}`] : [];
  // Development instances (pk_test_ keys) live under clerk.accounts.dev.
  if (!clerkHost || (clerkPublishableKey || '').startsWith('pk_test_')) {
    clerkOrigins.push(CLERK_DEV_INSTANCES);
  }

  const directives = {
    'default-src': ["'self'"],
    'script-src': [
      "'self'",
      "'unsafe-inline'",
      // The Next.js dev server evaluates code for hot reloading.
      ...(isDev ? ["'unsafe-eval'"] : []),
      ...clerkOrigins,
      CLOUDFLARE_CHALLENGES,
      umamiOrigin,
    ],
    'style-src': ["'self'", "'unsafe-inline'"],
    'img-src': ["'self'", 'data:', 'blob:', CLERK_IMAGES],
    'font-src': ["'self'", 'data:'],
    'connect-src': ["'self'", apiOrigin, ...clerkOrigins, CLERK_TELEMETRY, umamiOrigin],
    // Notebook pages show PDFs from blob: URLs in an iframe.
    'frame-src': ["'self'", 'blob:', CLOUDFLARE_CHALLENGES],
    'worker-src': ["'self'", 'blob:'],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'self'"],
  };

  return Object.entries(directives)
    .map(([name, values]) => [name, ...new Set(values.filter(Boolean))].join(' '))
    .join('; ');
}

/**
 * Headers for every dashboard response, as headers() in next.config.js expects.
 * The CSP is Report-Only unless CSP_ENFORCE=true; the others are always enforced.
 * @param {Record<string, string | undefined>} env usually process.env
 */
function buildSecurityHeaders(env) {
  const isDev = env.NODE_ENV === 'development';
  const policy = buildContentSecurityPolicy({
    apiUrl: env.NEXT_PUBLIC_API_URL,
    umamiUrl: env.NEXT_PUBLIC_UMAMI_URL,
    clerkPublishableKey: env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
    isDev,
  });
  const enforce = env.CSP_ENFORCE === 'true';

  return [
    {
      key: enforce ? 'Content-Security-Policy' : 'Content-Security-Policy-Report-Only',
      value: policy,
    },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    // Same value nginx already sends; the CSP's frame-ancestors only applies once enforced.
    { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
    ...(isDev ? [] : [{ key: 'Strict-Transport-Security', value: HSTS }]),
  ];
}

module.exports = { buildContentSecurityPolicy, buildSecurityHeaders, clerkFrontendApiFromKey };
