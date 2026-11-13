import { describe, it, expect } from 'vitest';
import { validateCallbackUrl, buildAgentRedirectUrl } from '@/lib/agent-callback';

describe('validateCallbackUrl', () => {
  it.each([
    ['http://localhost:5555/auth/callback'],
    ['http://127.0.0.1:5555/auth/callback'],
    ['http://localhost:61234/auth/callback'],
    ['http://localhost/auth/callback'],
  ])('accepts %s', (url) => {
    expect(validateCallbackUrl(url)).toBe(true);
  });

  it.each([
    ['non-http scheme with localhost authority (script)', 'javascript://localhost/%0aalert(1)'],
    ['non-http scheme with localhost authority (custom)', 'myapp://localhost/auth/callback'],
    ['https scheme', 'https://localhost:5555/auth/callback'],
    ['localhost as userinfo of another host', 'http://localhost@evil.com/'],
    ['localhost as userinfo with callback path', 'http://localhost@evil.com/auth/callback'],
    ['credentials on a local host', 'http://user:pw@localhost:5555/auth/callback'],
    ['local name as prefix of another domain', 'http://127.0.0.1.evil.com/'],
    ['local name as prefix of another domain with path', 'http://localhost.evil.com/auth/callback'],
    ['wrong path on local host', 'http://localhost:5555/other'],
    ['callback path as prefix only', 'http://localhost:5555/auth/callback/extra'],
    ['root path', 'http://localhost:5555/'],
    ['not a URL', 'not a url'],
    ['empty string', ''],
  ])('rejects %s', (_name, url) => {
    expect(validateCallbackUrl(url)).toBe(false);
  });
});

describe('buildAgentRedirectUrl', () => {
  it('sets the token as an encoded query parameter', () => {
    const out = buildAgentRedirectUrl('http://localhost:5555/auth/callback', 'a+b&c=d');
    expect(out).not.toBeNull();
    const u = new URL(out as string);
    expect(u.origin).toBe('http://localhost:5555');
    expect(u.pathname).toBe('/auth/callback');
    expect(u.searchParams.get('token')).toBe('a+b&c=d');
  });

  it('replaces an existing token parameter and keeps others', () => {
    const out = buildAgentRedirectUrl('http://127.0.0.1:5555/auth/callback?x=1&token=old', 'new');
    const u = new URL(out as string);
    expect(u.searchParams.getAll('token')).toEqual(['new']);
    expect(u.searchParams.get('x')).toBe('1');
  });

  it('keeps the agent state parameter unchanged', () => {
    // The agent sends ?callback=<encoded URL carrying its one-time state>
    const page = new URL(
      'https://dashboard.example/agent?callback=' +
        encodeURIComponent('http://localhost:5555/auth/callback?state=Ab-_9xYz'),
    );
    const callback = page.searchParams.get('callback') as string;
    expect(validateCallbackUrl(callback)).toBe(true);
    const out = buildAgentRedirectUrl(callback, 'tok');
    const u = new URL(out as string);
    expect(u.searchParams.get('state')).toBe('Ab-_9xYz');
    expect(u.searchParams.get('token')).toBe('tok');
  });

  it('returns null for a rejected callback', () => {
    expect(buildAgentRedirectUrl('javascript://localhost/%0aalert(1)', 't')).toBeNull();
    expect(buildAgentRedirectUrl('http://localhost:5555/other', 't')).toBeNull();
  });
});
