import { afterEach, describe, expect, it } from 'vitest';
import { queryClient } from '../../src/app/queryClient';
import { profileKeys } from '../../src/features/profiles/hooks';
import { clearAuthenticatedSession } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

afterEach(() => {
  queryClient.clear();
  useAuthStore.getState().setBootstrapping();
  localStorage.clear();
  sessionStorage.clear();
});

describe('profile cache and session isolation', () => {
  it('uses an authenticated user identity in every private profile cache key', () => {
    expect(profileKeys.my('user-a')).not.toEqual(profileKeys.my('user-b'));
  });

  it('removes private profile data when the authenticated session is cleared', async () => {
    const key = profileKeys.my('user-a');
    await queryClient.fetchQuery({
      queryKey: key,
      queryFn: async () => ({ displayName: 'Private profile data' }),
      meta: { private: true },
    });
    useAuthStore.getState().setAccessToken('memory-only-token');

    clearAuthenticatedSession();

    expect(queryClient.getQueryData(key)).toBeUndefined();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });
});
