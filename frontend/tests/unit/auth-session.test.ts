import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/app/queryClient';
import { CSRF_COOKIE_NAME } from '../../src/features/auth/cookies';
import {
  bootstrapSession,
  logoutAllSessions,
  logoutCurrentSession,
  resetBootstrapCoordinatorForTests,
} from '../../src/features/auth/session';
import type { AuthUser } from '../../src/features/auth/types';
import {
  apiClient,
  resetRefreshCoordinatorForTests,
  sessionClient,
} from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const originalAdapter = apiClient.defaults.adapter;
const userApiResponse = {
  id: 'synthetic-user',
  email: 'synthetic@example.test',
  phone_number: null,
  email_verified: true,
  phone_verified: false,
  account_status: 'ACTIVE',
  roles: ['BUYER'],
  created_at: '2026-01-01T00:00:00Z',
} as const;
const safeUser: AuthUser = {
  id: userApiResponse.id,
  email: userApiResponse.email,
  phoneNumber: userApiResponse.phone_number,
  emailVerified: userApiResponse.email_verified,
  phoneVerified: userApiResponse.phone_verified,
  accountStatus: userApiResponse.account_status,
  roles: [...userApiResponse.roles],
  createdAt: userApiResponse.created_at,
};

function response<T>(data: T, config?: InternalAxiosRequestConfig): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config: config ?? { headers: new AxiosHeaders() },
  };
}

function setCsrfCookie(value: string) {
  document.cookie = `${CSRF_COOKIE_NAME}=${encodeURIComponent(value)}; Path=/`;
}

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  document.cookie = `${CSRF_COOKIE_NAME}=; Max-Age=0; Path=/`;
  useAuthStore.getState().setBootstrapping();
  queryClient.clear();
  resetRefreshCoordinatorForTests();
  resetBootstrapCoordinatorForTests();
  vi.restoreAllMocks();
});

describe('session bootstrap', () => {
  it('rotates the browser session, loads /auth/me, and restores authenticated state', async () => {
    setCsrfCookie('csrf-value-a');
    const refresh = vi.spyOn(sessionClient, 'post').mockResolvedValue(
      response({ access_token: 'memory-value-b', token_type: 'bearer', expires_in: 900 }),
    );
    let meAuthorization: string | null = null;
    apiClient.defaults.adapter = (async (config) => {
      meAuthorization = AxiosHeaders.from(config.headers).get('Authorization')?.toString() ?? null;
      return response(userApiResponse, config);
    }) as AxiosAdapter;

    await bootstrapSession();

    expect(refresh).toHaveBeenCalledOnce();
    expect(refresh.mock.calls[0][0]).toBe('/auth/refresh');
    expect(meAuthorization).toBe('Bearer memory-value-b');
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: 'memory-value-b',
      user: safeUser,
      status: 'authenticated',
    });
  });

  it('settles as unauthenticated without a refresh request when no CSRF cookie exists', async () => {
    const refresh = vi.spyOn(sessionClient, 'post');

    await bootstrapSession();
    await bootstrapSession();

    expect(refresh).not.toHaveBeenCalled();
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });

  it('clears state when refresh fails', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('stale-memory-value', safeUser);
    vi.spyOn(sessionClient, 'post').mockRejectedValue(new AxiosError('Session unavailable'));

    await bootstrapSession();

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });

  it('rejects a malformed refresh response instead of creating partial auth state', async () => {
    setCsrfCookie('csrf-value-a');
    vi.spyOn(sessionClient, 'post').mockResolvedValue(
      response({ access_token: '', token_type: 'bearer', expires_in: 900 }),
    );

    await bootstrapSession();

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });

  it('does not retain the new token when /auth/me fails', async () => {
    setCsrfCookie('csrf-value-a');
    vi.spyOn(sessionClient, 'post').mockResolvedValue(
      response({ access_token: 'memory-value-b', token_type: 'bearer', expires_in: 900 }),
    );
    apiClient.defaults.adapter = (async () => {
      throw new AxiosError('Network unavailable');
    }) as AxiosAdapter;

    await bootstrapSession();

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });
});

describe('logout services', () => {
  function expiredBearer() {
    return new AxiosError('Expired access', undefined, undefined, undefined, {
      ...response(undefined), status: 401,
      headers: new AxiosHeaders({ 'WWW-Authenticate': 'Bearer' }),
    });
  }

  it('recovers an expired bearer once only to revoke all sessions without restoring auth', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('expired-memory-value', safeUser);
    queryClient.setQueryData(['auth', 'me'], safeUser);
    const request = vi.spyOn(sessionClient, 'post').mockImplementation(async (path) => {
      expect(useAuthStore.getState().accessToken).toBeNull();
      if (request.mock.calls.length === 1) throw expiredBearer();
      if (path === '/auth/refresh') return response({ access_token: 'revocation-only-token', token_type: 'bearer', expires_in: 900 });
      return response(undefined);
    });
    await logoutAllSessions();
    expect(request.mock.calls.map((call) => call[0])).toEqual(['/auth/logout-all', '/auth/refresh', '/auth/logout-all']);
    expect(AxiosHeaders.from(request.mock.calls[1][2]?.headers).get('X-CSRF-Token')).toBe('csrf-value-a');
    expect(AxiosHeaders.from(request.mock.calls[2][2]?.headers).get('Authorization')).toBe('Bearer revocation-only-token');
    expect(useAuthStore.getState().status).toBe('unauthenticated');
    expect(queryClient.getQueryData(['auth', 'me'])).toBeUndefined();
  });

  it('does not loop when the recovered logout-all bearer is rejected', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('expired-memory-value', safeUser);
    const request = vi.spyOn(sessionClient, 'post').mockImplementation(async (path) => {
      if (path === '/auth/refresh') return response({ access_token: 'revocation-only-token', token_type: 'bearer', expires_in: 900 });
      throw expiredBearer();
    });
    await expect(logoutAllSessions()).rejects.toBeInstanceOf(AxiosError);
    expect(request).toHaveBeenCalledTimes(3);
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('does not refresh logout-all without a browser session', async () => {
    const request = vi.spyOn(sessionClient, 'post').mockRejectedValue(expiredBearer());
    await expect(logoutAllSessions()).rejects.toBeInstanceOf(AxiosError);
    expect(request).toHaveBeenCalledOnce();
  });

  it('does not revoke a new account after the recovery response arrives late', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('expired-memory-value', safeUser);
    const request = vi.spyOn(sessionClient, 'post').mockImplementation(async (path) => {
      if (path === '/auth/logout-all') throw expiredBearer();
      useAuthStore.getState().setAuthenticated('new-account-token', { ...safeUser, id: 'other-user' });
      return response({ access_token: 'stale-recovery', token_type: 'bearer', expires_in: 900 });
    });
    await expect(logoutAllSessions()).rejects.toThrow('Session changed.');
    expect(request).toHaveBeenCalledTimes(2);
    expect(useAuthStore.getState().user?.id).toBe('other-user');
  });

  it('does not recover for network errors', async () => {
    setCsrfCookie('csrf-value-a');
    const request = vi.spyOn(sessionClient, 'post').mockRejectedValue(new AxiosError('Offline'));
    await expect(logoutAllSessions()).rejects.toBeInstanceOf(AxiosError);
    expect(request).toHaveBeenCalledOnce();
  });

  it('does not recover for a non-bearer challenge', async () => {
    setCsrfCookie('csrf-value-a');
    const error = expiredBearer();
    error.response!.headers = new AxiosHeaders({ 'WWW-Authenticate': 'Basic' });
    const request = vi.spyOn(sessionClient, 'post').mockRejectedValue(error);
    await expect(logoutAllSessions()).rejects.toBeInstanceOf(AxiosError);
    expect(request).toHaveBeenCalledOnce();
  });

  it('sends current CSRF, revokes the current session, and removes private cache', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    queryClient.setQueryData(['auth', 'me'], safeUser);
    const request = vi.spyOn(sessionClient, 'post').mockResolvedValue(response(undefined));

    await logoutCurrentSession();

    expect(request).toHaveBeenCalledOnce();
    expect(request.mock.calls[0][0]).toBe('/auth/logout');
    expect(request.mock.calls[0][1]).toBeUndefined();
    expect(AxiosHeaders.from(request.mock.calls[0][2]?.headers).get('X-CSRF-Token')).toBe(
      'csrf-value-a',
    );
    expect(queryClient.getQueryData(['auth', 'me'])).toBeUndefined();
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });

  it('still clears local auth when current-session logout cannot reach the server', async () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    vi.spyOn(sessionClient, 'post').mockRejectedValue(new AxiosError('Network unavailable'));

    await expect(logoutCurrentSession()).rejects.toBeInstanceOf(AxiosError);
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });

  it('logout-all sends only the bearer identity and clears local auth', async () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    const request = vi.spyOn(sessionClient, 'post').mockResolvedValue(response(undefined));

    await logoutAllSessions();

    expect(request).toHaveBeenCalledOnce();
    expect(request.mock.calls[0][0]).toBe('/auth/logout-all');
    expect(request.mock.calls[0][1]).toBeUndefined();
    expect(AxiosHeaders.from(request.mock.calls[0][2]?.headers).get('Authorization')).toBe(
      'Bearer memory-value-a',
    );
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });

  it('allows repeated idempotent local logout without refresh behavior', async () => {
    const request = vi.spyOn(sessionClient, 'post').mockResolvedValue(response(undefined));

    await logoutCurrentSession();
    await logoutCurrentSession();

    expect(request).toHaveBeenCalledTimes(2);
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });
});
