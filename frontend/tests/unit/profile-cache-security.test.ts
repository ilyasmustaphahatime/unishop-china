import { afterEach, describe, expect, it } from 'vitest';
import { vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import * as profileApi from '../../src/features/profiles/api';
import type { MyProfile } from '../../src/features/profiles/types';
import { queryClient } from '../../src/app/queryClient';
import { profileKeys, useUpdateProfile, useCompleteOnboarding } from '../../src/features/profiles/hooks';
import { clearAuthenticatedSession } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

afterEach(() => {
  queryClient.clear();
  useAuthStore.getState().setBootstrapping();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
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

  it.each(['update', 'complete'])('does not repopulate private cache after a late %s', async (action) => {
    const profile: MyProfile = {
      publicId: '4ecf6924-5957-4d9a-8326-a3459b9d2882', displayName: 'Audit User',
      bio: 'Private draft', city: 'Qingdao', onboardingCompleted: true,
      memberSince: '2026-01-01T00:00:00Z', createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z', emailVerified: false, phoneVerified: false,
    };
    useAuthStore.getState().setAuthenticated('audit-a', {
      id: 'audit-user-a', email: null, phoneNumber: null, accountStatus: 'ACTIVE',
      roles: ['BUYER'], emailVerified: false, phoneVerified: false, createdAt: profile.createdAt,
    });
    let resolve!: (value: MyProfile) => void;
    const pending = new Promise<MyProfile>((done) => { resolve = done; });
    vi.spyOn(profileApi, 'updateMyProfile').mockReturnValue(pending);
    vi.spyOn(profileApi, 'completeOnboarding').mockReturnValue(pending);
    const { result } = renderHook(() => ({ update: useUpdateProfile(), complete: useCompleteOnboarding() }), {
      wrapper: ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children),
    });
    let mutation!: Promise<MyProfile>;
    await act(async () => {
      mutation = action === 'update' ? result.current.update.mutateAsync({ bio: 'Private draft' }) : result.current.complete.mutateAsync();
      await Promise.resolve();
    });
    clearAuthenticatedSession();
    await act(async () => { resolve(profile); await mutation; });
    expect(queryClient.getQueryData(profileKeys.my('audit-user-a'))).toBeUndefined();
  });
});
