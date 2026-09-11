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
  return coordinateLogout(async () => {
    await sessionClient.post('/auth/logout-all', undefined, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    });
  });
}

export function resetBootstrapCoordinatorForTests() {
  bootstrapPromise = null;
}
