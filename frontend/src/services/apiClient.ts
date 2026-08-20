import axios, { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';
import { clearPrivateQueryCache } from '../app/queryClient';
import { refreshApiSchema } from '../features/auth/contracts';
import { readCsrfCookie } from '../features/auth/cookies';
import type { RefreshResponse } from '../features/auth/types';
import { useAuthStore } from '../stores/authStore';

type RetriableRequest = InternalAxiosRequestConfig & { _authRetried?: boolean };

const clientOptions = {
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
};

export const apiClient = axios.create(clientOptions);

// Refresh-cookie traffic has an explicit credential boundary and no bearer interceptor.
export const sessionClient = axios.create({ ...clientOptions, withCredentials: true });

let refreshPromise: Promise<RefreshResponse> | null = null;

function acceptsBearerToken(url: string | undefined): boolean {
  return !url?.startsWith('/auth/') || url === '/auth/me';
}

export function clearAuthenticatedSession() {
  useAuthStore.getState().clearSession();
  clearPrivateQueryCache();
}

export function refreshAccessToken(): Promise<RefreshResponse> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const csrfToken = readCsrfCookie();
    if (!csrfToken) throw new Error('No browser session is available.');

    const response = await sessionClient.post('/auth/refresh', undefined, {
      headers: { 'X-CSRF-Token': csrfToken },
    });
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
      clearAuthenticatedSession();
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token && acceptsBearerToken(config.url)) {
    config.headers = AxiosHeaders.from(config.headers);
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
      throw error;
    }

    const request = error.config as RetriableRequest;
    const challengeValue =
      error.response.headers instanceof AxiosHeaders
        ? error.response.headers.get('WWW-Authenticate')
        : error.response.headers['www-authenticate'];
    const challenge = challengeValue == null ? '' : String(challengeValue).toLowerCase();
    const hadBearer = Boolean(AxiosHeaders.from(request.headers).get('Authorization'));
    if (
      request._authRetried ||
      !hadBearer ||
      !challenge?.startsWith('bearer') ||
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
}
