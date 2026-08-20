import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CSRF_COOKIE_NAME,
  readCookie,
  readCsrfCookie,
} from '../../src/features/auth/cookies';

function clearCookie(name: string) {
  document.cookie = `${name}=; Max-Age=0; Path=/`;
}

afterEach(() => {
  clearCookie(CSRF_COOKIE_NAME);
  clearCookie('unishop_refresh_token');
  vi.restoreAllMocks();
});

describe('CSRF cookie reader', () => {
  it('reads only the requested, URL-decoded cookie', () => {
    document.cookie = `${CSRF_COOKIE_NAME}=${encodeURIComponent('synthetic value/with=symbols')}; Path=/`;
    document.cookie = 'unrelated=value; Path=/';

    expect(readCsrfCookie()).toBe('synthetic value/with=symbols');
    expect(readCookie('missing')).toBeNull();
  });

  it('does not intentionally read the refresh cookie', () => {
    document.cookie = 'unishop_refresh_token=not-an-auth-credential-in-this-test; Path=/';

    expect(readCsrfCookie()).toBeNull();
  });

  it('returns null for malformed encoding and performs no logging', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    document.cookie = `${CSRF_COOKIE_NAME}=%E0%A4%A; Path=/`;

    expect(readCsrfCookie()).toBeNull();
    expect(log).not.toHaveBeenCalled();
  });
});
