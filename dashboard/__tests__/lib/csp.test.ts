import { describe, it, expect } from 'vitest';
// lib/csp.js is CommonJS so next.config.js can require it at build time.
import csp from '../../lib/csp';

const { buildContentSecurityPolicy, buildSecurityHeaders, clerkFrontendApiFromKey } = csp;

// Publishable keys are "pk_<env>_" + base64("<frontend api host>$").
const key = (env: 'test' | 'live', host: string) =>
  `pk_${env}_${Buffer.from(`${host}$`).toString('base64')}`;

const TEST_KEY = key('test', 'example-app-12.clerk.accounts.dev');
const LIVE_KEY = key('live', 'clerk.example.com');

function directives(policy: string): Record<string, string[]> {
  return Object.fromEntries(
    policy.split(';').map((d) => {
      const [name, ...values] = d.trim().split(/\s+/);
      return [name, values];
    })
  );
}

function header(headers: { key: string; value: string }[], name: string) {
  return headers.find((h) => h.key.toLowerCase() === name.toLowerCase())?.value;
}

describe('clerkFrontendApiFromKey', () => {
  it('decodes the frontend API host from test and live keys', () => {
    expect(clerkFrontendApiFromKey(TEST_KEY)).toBe('example-app-12.clerk.accounts.dev');
    expect(clerkFrontendApiFromKey(LIVE_KEY)).toBe('clerk.example.com');
  });

  it('returns null for missing or malformed keys', () => {
    expect(clerkFrontendApiFromKey(undefined)).toBeNull();
    expect(clerkFrontendApiFromKey('')).toBeNull();
    expect(clerkFrontendApiFromKey('not-a-key')).toBeNull();
    expect(clerkFrontendApiFromKey('pk_live_' + Buffer.from('bad host;$').toString('base64'))).toBeNull();
  });
});

describe('buildContentSecurityPolicy', () => {
  const base = {
    apiUrl: 'https://api.example.com/api/v1',
    umamiUrl: 'https://stats.example.com',
    clerkPublishableKey: LIVE_KEY,
    isDev: false,
  };

  it('allows self, the API origin, Clerk and Umami', () => {
    const d = directives(buildContentSecurityPolicy(base));

    expect(d['default-src']).toEqual(["'self'"]);
    expect(d['script-src']).toEqual(
      expect.arrayContaining([
        "'self'",
        'https://clerk.example.com',
        'https://challenges.cloudflare.com',
        'https://stats.example.com',
      ])
    );
    expect(d['connect-src']).toEqual(
      expect.arrayContaining([
        "'self'",
        'https://api.example.com',
        'https://clerk.example.com',
        'https://stats.example.com',
      ])
    );
    expect(d['img-src']).toContain('https://img.clerk.com');
    expect(d['worker-src']).toEqual(["'self'", 'blob:']);
    expect(d['style-src']).toEqual(["'self'", "'unsafe-inline'"]);
    expect(d['frame-src']).toEqual(
      expect.arrayContaining(['blob:', 'https://challenges.cloudflare.com'])
    );
    expect(d['frame-ancestors']).toEqual(["'self'"]);
    expect(d['object-src']).toEqual(["'none'"]);
    expect(d['base-uri']).toEqual(["'self'"]);
    expect(d['form-action']).toEqual(["'self'"]);
  });

  it('uses only the origin of the API URL, not its path', () => {
    const policy = buildContentSecurityPolicy(base);
    expect(policy).not.toContain('/api/v1');
  });

  it('never allows arbitrary hosts or eval in production', () => {
    const d = directives(buildContentSecurityPolicy(base));
    for (const name of ['script-src', 'connect-src', 'default-src']) {
      expect(d[name]).not.toContain('https:');
      expect(d[name]).not.toContain('http:');
      expect(d[name]).not.toContain('*');
    }
    expect(d['script-src']).not.toContain("'unsafe-eval'");
    // Clerk dev-instance wildcard is only for test keys
    expect(d['script-src']).not.toContain('https://*.clerk.accounts.dev');
  });

  it('adds the Clerk dev-instance hosts for test keys', () => {
    const d = directives(buildContentSecurityPolicy({ ...base, clerkPublishableKey: TEST_KEY }));
    expect(d['script-src']).toEqual(
      expect.arrayContaining([
        'https://example-app-12.clerk.accounts.dev',
        'https://*.clerk.accounts.dev',
      ])
    );
    expect(d['connect-src']).toContain('https://*.clerk.accounts.dev');
  });

  it("allows 'unsafe-eval' only in development (Next.js dev server needs it)", () => {
    const d = directives(buildContentSecurityPolicy({ ...base, isDev: true }));
    expect(d['script-src']).toContain("'unsafe-eval'");
  });

  it('skips Umami and falls back to the default API URL when unset', () => {
    const policy = buildContentSecurityPolicy({
      ...base,
      apiUrl: undefined,
      umamiUrl: undefined,
    });
    expect(policy).not.toContain('stats.example.com');
    expect(directives(policy)['connect-src']).toContain('https://rmirror.io');
    expect(policy).not.toContain('undefined');
  });

  it('ignores a malformed Umami URL instead of emitting it', () => {
    const policy = buildContentSecurityPolicy({ ...base, umamiUrl: 'not a url' });
    expect(policy).not.toContain('not a url');
  });
});

describe('buildSecurityHeaders', () => {
  const env = {
    NEXT_PUBLIC_API_URL: 'https://api.example.com/api/v1',
    NEXT_PUBLIC_UMAMI_URL: 'https://stats.example.com',
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: LIVE_KEY,
    NODE_ENV: 'production',
  };

  it('ships the CSP as Report-Only by default', () => {
    const headers = buildSecurityHeaders(env);
    expect(header(headers, 'Content-Security-Policy-Report-Only')).toContain("default-src 'self'");
    expect(header(headers, 'Content-Security-Policy')).toBeUndefined();
  });

  it('enforces the CSP when CSP_ENFORCE=true', () => {
    const headers = buildSecurityHeaders({ ...env, CSP_ENFORCE: 'true' });
    expect(header(headers, 'Content-Security-Policy')).toContain("default-src 'self'");
    expect(header(headers, 'Content-Security-Policy-Report-Only')).toBeUndefined();
  });

  it('always enforces the other security headers', () => {
    const headers = buildSecurityHeaders(env);
    expect(header(headers, 'Referrer-Policy')).toBe('strict-origin-when-cross-origin');
    expect(header(headers, 'X-Content-Type-Options')).toBe('nosniff');
    expect(header(headers, 'X-Frame-Options')).toBe('SAMEORIGIN');
    expect(header(headers, 'Strict-Transport-Security')).toBe(
      'max-age=31536000; includeSubDomains'
    );
  });

  it('omits HSTS on the development server', () => {
    const headers = buildSecurityHeaders({ ...env, NODE_ENV: 'development' });
    expect(header(headers, 'Strict-Transport-Security')).toBeUndefined();
  });
});
