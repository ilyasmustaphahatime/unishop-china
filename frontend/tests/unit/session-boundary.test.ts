import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/app/queryClient';
import { CSRF_COOKIE_NAME } from '../../src/features/auth/cookies';
import { bootstrapSession, logoutCurrentSession, resetBootstrapCoordinatorForTests } from '../../src/features/auth/session';
import { login } from '../../src/features/auth/api';
import type { AuthUser } from '../../src/features/auth/types';
import { apiClient, clearAuthenticatedSession, refreshAccessToken, resetRefreshCoordinatorForTests, sessionClient } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const originalAdapter = apiClient.defaults.adapter;
const user: AuthUser = {
  id: 'audit-user-a', email: null, phoneNumber: null, roles: ['BUYER'],
  accountStatus: 'ACTIVE', emailVerified: false, phoneVerified: false,
  createdAt: '2026-01-01T00:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}

function response(data: unknown, config?: InternalAxiosRequestConfig): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config: config ?? { headers: new AxiosHeaders() } };
}

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  document.cookie = `${CSRF_COOKIE_NAME}=; Max-Age=0; Path=/`;
  useAuthStore.getState().setBootstrapping();
  resetRefreshCoordinatorForTests();
  resetBootstrapCoordinatorForTests();
  queryClient.clear();
  vi.restoreAllMocks();
});

describe('responses cannot cross a session boundary', () => {
  it('rejects a refresh response that arrives after logout', async () => {
    document.cookie = `${CSRF_COOKIE_NAME}=audit-placeholder; Path=/`;
    useAuthStore.getState().setAuthenticated('audit-a', user);
    const pending = deferred<AxiosResponse>();
    vi.spyOn(sessionClient, 'post').mockReturnValue(pending.promise);
    const outcome = refreshAccessToken().then(() => 'accepted', () => 'rejected');
    clearAuthenticatedSession();
    pending.resolve(response({ access_token: 'audit-late', token_type: 'bearer', expires_in: 900 }));
    expect(await outcome).toBe('rejected');
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('does not let an old refresh failure clear a new user session', async () => {
    document.cookie = `${CSRF_COOKIE_NAME}=audit-placeholder; Path=/`;
    useAuthStore.getState().setAuthenticated('audit-a', user);
    const pending = deferred<AxiosResponse>();
    vi.spyOn(sessionClient, 'post').mockReturnValue(pending.promise);
    const outcome = refreshAccessToken().catch(() => undefined);
    clearAuthenticatedSession();
    useAuthStore.getState().setAuthenticated('audit-b', { ...user, id: 'audit-user-b' });
    pending.reject(new Error('Controlled network failure'));
    await outcome;
    expect(useAuthStore.getState().user?.id).toBe('audit-user-b');
  });

  it('never retries an old user mutation with the new user bearer', async () => {
    document.cookie = `${CSRF_COOKIE_NAME}=audit-placeholder; Path=/`;
    useAuthStore.getState().setAuthenticated('audit-a', user);
    const started = deferred<InternalAxiosRequestConfig>();
    const pending = deferred<AxiosResponse>();
    let calls = 0;
    apiClient.defaults.adapter = async (config) => {
      calls += 1;
      if (calls === 1) { started.resolve(config); return pending.promise; }
      return response({}, config);
    };
    const refresh = vi.spyOn(sessionClient, 'post').mockResolvedValue(response({ access_token: 'audit-b-refresh', token_type: 'bearer', expires_in: 900 }));
    const outcome = apiClient.patch('/profile/me', { bio: 'User A data' }).catch(() => undefined);
    const config = await started.promise;
    clearAuthenticatedSession();
    useAuthStore.getState().setAuthenticated('audit-b', { ...user, id: 'audit-user-b' });
    pending.reject(new AxiosError('Unauthorized', undefined, config, undefined, {
      ...response({}, config), status: 401, headers: new AxiosHeaders({ 'WWW-Authenticate': 'Bearer' }),
    }));
    await outcome;
    expect(calls).toBe(1);
    expect(refresh).not.toHaveBeenCalled();
    expect(useAuthStore.getState().user?.id).toBe('audit-user-b');
  });

  it('does not restore bootstrap user data after logout', async () => {
    document.cookie = `${CSRF_COOKIE_NAME}=audit-placeholder; Path=/`;
    const started = deferred<void>();
    const pending = deferred<AxiosResponse>();
    vi.spyOn(sessionClient, 'post').mockResolvedValue(response({ access_token: 'audit-a', token_type: 'bearer', expires_in: 900 }));
    apiClient.defaults.adapter = async () => { started.resolve(); return pending.promise; };
    const boot = bootstrapSession();
    await started.promise;
    clearAuthenticatedSession();
    pending.resolve(response({ id: user.id, email: null, phone_number: null, roles: ['BUYER'], account_status: 'ACTIVE', email_verified: false, phone_verified: false, created_at: user.createdAt }));
    await boot;
    expect(useAuthStore.getState().status).toBe('unauthenticated');
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('clears a private profile cache entry created by a mutation without query metadata', () => {
    queryClient.setQueryData(['profile', 'me', user.id], { bio: 'Private draft' });
    clearAuthenticatedSession();
    expect(queryClient.getQueryData(['profile', 'me', user.id])).toBeUndefined();
  });

  it('waits for a dispatched refresh before revoking its replacement cookie', async () => {
    document.cookie = `${CSRF_COOKIE_NAME}=audit-placeholder; Path=/`;
    useAuthStore.getState().setAuthenticated('audit-a', user);
    const pending = deferred<AxiosResponse>();
    const post = vi.spyOn(sessionClient, 'post').mockImplementation(async (path) => {
      if (path === '/auth/refresh') return pending.promise;
      return response(undefined);
    });
    const refresh = refreshAccessToken().catch(() => undefined);
    const logout = logoutCurrentSession();
    expect(post).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    document.cookie = `${CSRF_COOKIE_NAME}=rotated-audit-placeholder; Path=/`;
    pending.resolve(response({ access_token: 'audit-late', token_type: 'bearer', expires_in: 900 }));
    await Promise.all([refresh, logout]);
    expect(post.mock.calls[1][0]).toBe('/auth/logout');
    expect(AxiosHeaders.from(post.mock.calls[1][2]?.headers).get('X-CSRF-Token')).toBe('rotated-audit-placeholder');
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('rejects late successful private responses after an account switch', async () => {
    useAuthStore.getState().setAuthenticated('audit-a', user);
    const started = deferred<InternalAxiosRequestConfig>();
    const pending = deferred<AxiosResponse>();
    apiClient.defaults.adapter = async (config) => { started.resolve(config); return pending.promise; };
    const outcome = apiClient.get('/profile/me').then(() => 'accepted', () => 'rejected');
    const config = await started.promise;
    useAuthStore.getState().setAuthenticated('audit-b', { ...user, id: 'audit-user-b' });
    pending.resolve(response({ bio: 'Old private data' }, config));
    expect(await outcome).toBe('rejected');
  });

  it('does not attach a bearer to external URLs', async () => {
    useAuthStore.getState().setAuthenticated('audit-a', user);
    apiClient.defaults.adapter = async (config) => {
      expect(AxiosHeaders.from(config.headers).has('Authorization')).toBe(false);
      return response({}, config);
    };
    await apiClient.get('https://attacker.example/resource');
    await apiClient.get('//attacker.example/resource');
  });

  it('rejects a login response invalidated while it was in flight', async () => {
    const started = deferred<void>();
    const pending = deferred<AxiosResponse>();
    vi.spyOn(sessionClient, 'post').mockImplementation(async () => { started.resolve(); return pending.promise; });
    const outcome = login({ identifier: 'audit@example.com', password: 'test-only-placeholder' }).then(() => 'accepted', () => 'rejected');
    await started.promise;
    clearAuthenticatedSession();
    pending.resolve(response({}));
    expect(await outcome).toBe('rejected');
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });
});
