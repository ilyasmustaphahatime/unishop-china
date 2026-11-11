import axios, { AxiosHeaders } from 'axios';
import {
  clearAuthenticatedSession,
  coordinateLogout,
  currentSessionVersion,
  requireCurrentSession,
  refreshAccessToken,
  sessionClient,
} from '../../services/apiClient';
import { useAuthStore } from '../../stores/authStore';
import { getCurrentUser } from './api';
import { readCsrfCookie } from './cookies';
import { refreshApiSchema } from './contracts';

let bootstrapPromise: Promise<void> | null = null;

export function bootstrapSession(): Promise<void> {
  if (bootstrapPromise) return bootstrapPromise;
  const version = currentSessionVersion();

  bootstrapPromise = (async () => {
    if (!readCsrfCookie()) {
      clearAuthenticatedSession();
      return;
    }

    try {
      const session = await refreshAccessToken();
      const user = await getCurrentUser();
      requireCurrentSession(version);
      useAuthStore.getState().setAuthenticated(session.accessToken, user);
    } catch {
      if (version === currentSessionVersion()) clearAuthenticatedSession();
    }
  })().finally(() => {
    bootstrapPromise = null;
  });

  return bootstrapPromise;
}

export async function logoutCurrentSession(): Promise<void> {
  return coordinateLogout(async () => {
    const csrfToken = readCsrfCookie();
    await sessionClient.post('/auth/logout', undefined, {
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : undefined,
    });
  });
}

export async function logoutAllSessions(): Promise<void> {
  const accessToken = useAuthStore.getState().accessToken;
  return coordinateLogout(async (version) => {
    try {
      await sessionClient.post('/auth/logout-all', undefined, {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      });
    } catch (error) {
      const headers = axios.isAxiosError(error) ? error.response?.headers : undefined;
      const challenge = headers instanceof AxiosHeaders
        ? headers.get('WWW-Authenticate') : headers?.['www-authenticate'];
      const csrfToken = readCsrfCookie();
      if (!axios.isAxiosError(error) || error.response?.status !== 401
        || !/^bearer(?:\s|$)/i.test(String(challenge ?? '')) || !csrfToken) throw error;
      requireCurrentSession(version);
      // Recover authority once solely to revoke it. Never restore signed-in
      // state or use the general refresh coordinator while logout is running.
      const refreshed = await sessionClient.post('/auth/refresh', undefined, {
        headers: { 'X-CSRF-Token': csrfToken },
      });
      requireCurrentSession(version);
      const token = refreshApiSchema.parse(refreshed.data).access_token;
      await sessionClient.post('/auth/logout-all', undefined, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });
}

export function resetBootstrapCoordinatorForTests() {
  bootstrapPromise = null;
}
