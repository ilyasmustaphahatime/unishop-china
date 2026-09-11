import axios, { AxiosHeaders, CanceledError, type InternalAxiosRequestConfig } from 'axios';
import { clearPrivateQueryCache } from '../app/queryClient';
import { refreshApiSchema } from '../features/auth/contracts';
import { readCsrfCookie } from '../features/auth/cookies';
import type { RefreshResponse } from '../features/auth/types';
import { useAuthStore } from '../stores/authStore';

type RetriableRequest = InternalAxiosRequestConfig & {
  _authRetried?: boolean;
  _authSessionVersion?: number;
};

const clientOptions = {
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
};

export const apiClient = axios.create(clientOptions);

// Refresh-cookie traffic has an explicit credential boundary and no bearer interceptor.
export const sessionClient = axios.create({ ...clientOptions, withCredentials: true });

let refreshPromise: Promise<RefreshResponse> | null = null;
let refreshVersion: number | null = null;
let logoutPromise: Promise<void> | null = null;

export function currentSessionVersion() {
  return useAuthStore.getState().sessionVersion;
}

export function requireCurrentSession(version: number) {
  if (version !== currentSessionVersion()) throw new CanceledError('Session changed.');
}

export async function settleSessionRequests() {
  if (logoutPromise) await logoutPromise.catch(() => undefined);
  if (refreshPromise) await refreshPromise.catch(() => undefined);
}

export function coordinateLogout(revoke: () => Promise<void>): Promise<void> {
  if (logoutPromise) return logoutPromise;
  clearAuthenticatedSession();
  const version = currentSessionVersion();
  logoutPromise = (async () => {
    // Let an already-dispatched rotation finish setting its cookie before revoking it.
    if (refreshPromise) await refreshPromise.catch(() => undefined);
    await revoke();
  })().finally(() => {
    if (version === currentSessionVersion()) clearAuthenticatedSession();
    logoutPromise = null;
  });
  return logoutPromise;
}

function acceptsBearerToken(url: string | undefined): boolean {
  return Boolean(url?.startsWith('/') && !url.startsWith('//') &&
    (!url.startsWith('/auth/') || url === '/auth/me'));
}

export function clearAuthenticatedSession() {
  useAuthStore.getState().clearSession();
  clearPrivateQueryCache();
}

export function refreshAccessToken(): Promise<RefreshResponse> {
  if (logoutPromise) return Promise.reject(new CanceledError('Sign out is in progress.'));
  const version = currentSessionVersion();
  if (refreshPromise && refreshVersion === version) return refreshPromise;
  refreshVersion = version;

  refreshPromise = (async () => {
    const csrfToken = readCsrfCookie();
    if (!csrfToken) throw new Error('No browser session is available.');

    const response = await sessionClient.post('/auth/refresh', undefined, {
      headers: { 'X-CSRF-Token': csrfToken },
    });
    requireCurrentSession(version);
    const data = refreshApiSchema.parse(response.data);
    const session: RefreshResponse = {
      accessToken: data.access_token,
      tokenType: data.token_type,
      expiresIn: data.expires_in,
    };
    useAuthStore.getState().setAccessToken(session.accessToken);
    return session;
  })()
    .catch((error: unknown) => {
      if (version === currentSessionVersion()) clearAuthenticatedSession();
      throw error;
    })
    .finally(() => {
      if (refreshVersion === version) {
        refreshPromise = null;
        refreshVersion = null;
      }
    });

  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const request = config as RetriableRequest;
  request._authSessionVersion ??= currentSessionVersion();
  requireCurrentSession(request._authSessionVersion);
  const token = useAuthStore.getState().accessToken;
  if (token && acceptsBearerToken(config.url)) {
    config.headers = AxiosHeaders.from(config.headers);
    config.headers.set('Authorization', `Bearer ${token}`);
  } else {
    config.headers = AxiosHeaders.from(config.headers);
    config.headers.delete('Authorization');
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    const version = (response.config as RetriableRequest)._authSessionVersion;
    if (version !== undefined) requireCurrentSession(version);
    return response;
  },
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
      throw error;
    }

    const request = error.config as RetriableRequest;
    if (request._authSessionVersion !== undefined) requireCurrentSession(request._authSessionVersion);
    const challengeValue =
      error.response.headers instanceof AxiosHeaders
        ? error.response.headers.get('WWW-Authenticate')
        : error.response.headers['www-authenticate'];
    const challenge = challengeValue == null ? '' : String(challengeValue).toLowerCase();
    const hadBearer = Boolean(AxiosHeaders.from(request.headers).get('Authorization'));
    if (
      request._authRetried ||
      !hadBearer ||
      !/^bearer(?:\s|$)/.test(challenge) ||
      !acceptsBearerToken(request.url)
    ) {
      if (request._authRetried) clearAuthenticatedSession();
      throw error;
    }

    request._authRetried = true;
    const refreshed = await refreshAccessToken();
    request.headers = AxiosHeaders.from(request.headers);
    request.headers.set('Authorization', `Bearer ${refreshed.accessToken}`);
    return apiClient(request);
  },
);

export function resetRefreshCoordinatorForTests() {
  refreshPromise = null;
  refreshVersion = null;
  logoutPromise = null;
}
