import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearAuthenticatedSession } from '../../src/services/apiClient';
import { queryClient } from '../../src/app/queryClient';
import type { AuthUser } from '../../src/features/auth/types';
import { useAuthStore } from '../../src/stores/authStore';

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

afterEach(() => {
  useAuthStore.getState().setBootstrapping();
  queryClient.clear();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('Phase 4C authentication state security', () => {
  it('starts in the bootstrapping lifecycle state', () => {
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'bootstrapping',
    });
  });

  it('keeps the access token and safe user in memory without browser storage writes', () => {
    const localWrite = vi.spyOn(Storage.prototype, 'setItem');
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: 'memory-value-a',
      user: safeUser,
      status: 'authenticated',
    });
    expect(localWrite).not.toHaveBeenCalled();
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });

  it('clears token, user, and only private query data', () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    queryClient.setQueryData(['auth', 'me'], safeUser);
    queryClient.setQueryData(['marketplace', 'public'], ['safe-public-data']);

    clearAuthenticatedSession();

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
    expect(queryClient.getQueryData(['auth', 'me'])).toBeUndefined();
    expect(queryClient.getQueryData(['marketplace', 'public'])).toEqual(['safe-public-data']);
  });
});
