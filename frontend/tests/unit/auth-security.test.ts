import { afterEach, describe, expect, it } from 'vitest';
import { useAuthStore } from '../../src/stores/authStore';

afterEach(() => {
  useAuthStore.getState().logout();
  localStorage.clear();
  sessionStorage.clear();
});

describe('pre-Phase-4 authentication scaffold security', () => {
  it('keeps a simulated session in memory and writes no browser storage', () => {
    useAuthStore.getState().completeLogin({
      accessToken: 'test-only-access-token',
      tokenType: 'bearer',
      user: {
        id: 'test-user',
        displayName: 'Test User',
        roles: ['BUYER'],
      },
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });

  it('clears all in-memory authentication state on logout', () => {
    useAuthStore.getState().completeLogin({
      accessToken: 'test-only-access-token',
      tokenType: 'bearer',
      user: {
        id: 'test-user',
        displayName: 'Test User',
        roles: ['BUYER'],
      },
    });

    useAuthStore.getState().logout();

    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      roles: [],
      isAuthenticated: false,
    });
  });
});
