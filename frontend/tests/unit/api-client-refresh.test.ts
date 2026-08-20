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
import type { AuthUser } from '../../src/features/auth/types';
import {
  apiClient,
  refreshAccessToken,
  resetRefreshCoordinatorForTests,
  sessionClient,
} from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const originalAdapter = apiClient.defaults.adapter;
const safeUser: AuthUser = {
  id: 'synthetic-user',
  email: 'synthetic@example.test',
  phoneNumber: null,
  emailVerified: false,
  phoneVerified: false,
  accountStatus: 'ACTIVE',
  roles: ['BUYER'],
  createdAt: '2026-01-01T00:00:00Z',
};

function setCsrfCookie(value: string) {
  document.cookie = `${CSRF_COOKIE_NAME}=${encodeURIComponent(value)}; Path=/`;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function response<T>(data: T, config?: InternalAxiosRequestConfig): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config: config ?? { headers: new AxiosHeaders() },
  };
}

function unauthorized(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError(
    'Unauthorized',
    AxiosError.ERR_BAD_REQUEST,
    config,
    undefined,
    {
      data: { detail: 'Authentication required.' },
      status: 401,
      statusText: 'Unauthorized',
      headers: new AxiosHeaders({ 'WWW-Authenticate': 'Bearer' }),
      config,
    },
  );
}

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  document.cookie = `${CSRF_COOKIE_NAME}=; Max-Age=0; Path=/`;
  useAuthStore.getState().setBootstrapping();
  queryClient.clear();
  resetRefreshCoordinatorForTests();
  vi.restoreAllMocks();
});

describe('HTTP authentication boundaries', () => {
  it('uses credentials only on the session client and injects bearer dynamically', async () => {
    const headersByPath = new Map<string, string | null>();
    apiClient.defaults.adapter = (async (config) => {
      headersByPath.set(
        config.url ?? '',
        AxiosHeaders.from(config.headers).get('Authorization')?.toString() ?? null,
      );
      return response({}, config);
    }) as AxiosAdapter;
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);

    await apiClient.get('/products/private');
    await apiClient.post('/auth/register', { email: 'synthetic@example.test' });

    expect(apiClient.defaults.withCredentials).not.toBe(true);
    expect(sessionClient.defaults.withCredentials).toBe(true);
    expect(headersByPath.get('/products/private')).toBe('Bearer memory-value-a');
    expect(headersByPath.get('/auth/register')).toBeNull();
  });

  it('does not auto-refresh a public authentication endpoint', async () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    apiClient.defaults.adapter = (async (config) => {
      throw unauthorized(config);
    }) as AxiosAdapter;
    const refresh = vi.spyOn(sessionClient, 'post');

    await expect(apiClient.post('/auth/phone/verify', {})).rejects.toBeInstanceOf(AxiosError);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('does not treat an unrelated 401 without a Bearer challenge as token expiry', async () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    apiClient.defaults.adapter = (async (config) => {
      const error = unauthorized(config);
      if (error.response) error.response.headers = new AxiosHeaders();
      throw error;
    }) as AxiosAdapter;
    const refresh = vi.spyOn(sessionClient, 'post');

    await expect(apiClient.get('/protected-resource')).rejects.toBeInstanceOf(AxiosError);
    expect(refresh).not.toHaveBeenCalled();
    expect(useAuthStore.getState().status).toBe('authenticated');
  });
});

describe('single-flight access-token refresh', () => {
  it('refreshes once and retries five waiting requests with the new token', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    const refreshResult = deferred<AxiosResponse>();
    const refreshStarted = deferred<void>();
    const allInitialRequests = deferred<void>();
    let initialCount = 0;
    let adapterCalls = 0;
    const retryHeaders: Array<string | null> = [];
    const retryParams: unknown[] = [];

    const refresh = vi.spyOn(sessionClient, 'post').mockImplementation(() => {
      refreshStarted.resolve();
      return refreshResult.promise;
    });
    apiClient.defaults.adapter = (async (config) => {
      adapterCalls += 1;
      const authorization = AxiosHeaders.from(config.headers).get('Authorization')?.toString() ?? null;
      if (authorization === 'Bearer memory-value-a') {
        initialCount += 1;
        if (initialCount === 5) allInitialRequests.resolve();
        throw unauthorized(config);
      }
      retryHeaders.push(authorization);
      retryParams.push(config.params);
      return response({ ok: true }, config);
    }) as AxiosAdapter;

    const requests = Array.from({ length: 5 }, (_, id) =>
      apiClient.get('/protected-resource', { params: { id } }),
    );
    await allInitialRequests.promise;
    await refreshStarted.promise;
    await Promise.resolve();
    await Promise.resolve();
    expect(refresh).toHaveBeenCalledTimes(1);

    refreshResult.resolve(
      response({ access_token: 'memory-value-b', token_type: 'bearer', expires_in: 900 }),
    );
    const results = await Promise.all(requests);

    expect(results).toHaveLength(5);
    expect(adapterCalls).toBe(10);
    expect(retryHeaders).toEqual(Array(5).fill('Bearer memory-value-b'));
    expect(retryParams).toEqual(Array.from({ length: 5 }, (_, id) => ({ id })));
    expect(useAuthStore.getState().accessToken).toBe('memory-value-b');
  });

  it('rejects all five waiters and clears state when the one refresh fails', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    const refreshResult = deferred<AxiosResponse>();
    const refreshStarted = deferred<void>();
    const allInitialRequests = deferred<void>();
    let initialCount = 0;
    let adapterCalls = 0;
    const clearSession = vi.spyOn(useAuthStore.getState(), 'clearSession');

    const refresh = vi.spyOn(sessionClient, 'post').mockImplementation(() => {
      refreshStarted.resolve();
      return refreshResult.promise;
    });
    apiClient.defaults.adapter = (async (config) => {
      adapterCalls += 1;
      initialCount += 1;
      if (initialCount === 5) allInitialRequests.resolve();
      throw unauthorized(config);
    }) as AxiosAdapter;

    const requests = Array.from({ length: 5 }, () => apiClient.get('/protected-resource'));
    await allInitialRequests.promise;
    await refreshStarted.promise;
    await Promise.resolve();
    await Promise.resolve();
    refreshResult.reject(new AxiosError('Refresh unavailable'));
    const results = await Promise.allSettled(requests);

    expect(results.every((result) => result.status === 'rejected')).toBe(true);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(adapterCalls).toBe(5);
    expect(clearSession).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });

  it('retries an original request only once when the retry is also unauthorized', async () => {
    setCsrfCookie('csrf-value-a');
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    let adapterCalls = 0;
    apiClient.defaults.adapter = (async (config) => {
      adapterCalls += 1;
      throw unauthorized(config);
    }) as AxiosAdapter;
    const refresh = vi.spyOn(sessionClient, 'post').mockResolvedValue(
      response({ access_token: 'memory-value-b', token_type: 'bearer', expires_in: 900 }),
    );

    await expect(apiClient.get('/protected-resource')).rejects.toBeInstanceOf(AxiosError);

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(adapterCalls).toBe(2);
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });

  it('re-reads the rotated CSRF cookie for every refresh', async () => {
    const seenHeaders: Array<string | null> = [];
    vi.spyOn(sessionClient, 'post').mockImplementation((_url, _data, config) => {
      seenHeaders.push(
        AxiosHeaders.from(config?.headers).get('X-CSRF-Token')?.toString() ?? null,
      );
      return Promise.resolve(
        response({ access_token: `memory-value-${seenHeaders.length}`, token_type: 'bearer', expires_in: 900 }),
      );
    });

    setCsrfCookie('csrf-value-a');
    await refreshAccessToken();
    setCsrfCookie('csrf-value-b');
    await refreshAccessToken();

    expect(seenHeaders).toEqual(['csrf-value-a', 'csrf-value-b']);
  });
});
