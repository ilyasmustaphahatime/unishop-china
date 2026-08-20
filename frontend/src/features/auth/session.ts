import {
  clearAuthenticatedSession,
  refreshAccessToken,
  sessionClient,
} from '../../services/apiClient';
import { useAuthStore } from '../../stores/authStore';
import { getCurrentUser } from './api';
import { readCsrfCookie } from './cookies';

let bootstrapPromise: Promise<void> | null = null;

export function bootstrapSession(): Promise<void> {
  if (bootstrapPromise) return bootstrapPromise;

  bootstrapPromise = (async () => {
    if (!readCsrfCookie()) {
      clearAuthenticatedSession();
      return;
    }

    try {
      const session = await refreshAccessToken();
      const user = await getCurrentUser();
      useAuthStore.getState().setAuthenticated(session.accessToken, user);
    } catch {
      clearAuthenticatedSession();
    }
  })().finally(() => {
    bootstrapPromise = null;
  });

  return bootstrapPromise;
}

export async function logoutCurrentSession(): Promise<void> {
  try {
    const csrfToken = readCsrfCookie();
    await sessionClient.post('/auth/logout', undefined, {
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : undefined,
    });
  } finally {
    clearAuthenticatedSession();
  }
}

export async function logoutAllSessions(): Promise<void> {
  const accessToken = useAuthStore.getState().accessToken;
  try {
    await sessionClient.post('/auth/logout-all', undefined, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    });
  } finally {
    clearAuthenticatedSession();
  }
}

export function resetBootstrapCoordinatorForTests() {
  bootstrapPromise = null;
}
