import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import {
  completeOnboarding,
  getMyProfile,
  getPublicProfile,
  updateMyProfile,
} from './api';

export const profileKeys = {
  my: (userId: string | undefined) => ['profile', 'me', userId] as const,
  public: (publicId: string) => ['profile', 'public', publicId] as const,
};

export function useMyProfile() {
  const userId = useAuthStore((state) => state.user?.id);
  const authenticated = useAuthStore((state) => state.status === 'authenticated');
  return useQuery({
    queryKey: profileKeys.my(userId),
    queryFn: getMyProfile,
    enabled: authenticated && Boolean(userId),
    meta: { private: true },
    staleTime: 30_000,
    retry: 1,
  });
}

export function useUpdateProfile() {
  const userId = useAuthStore((state) => state.user?.id);
  const queryClient = useQueryClient();
  const version = useAuthStore((state) => state.sessionVersion);
  return useMutation({
    mutationFn: (input: Parameters<typeof updateMyProfile>[0]) => {
      requireCurrentSession(version);
      return updateMyProfile(input);
    },
    onSuccess: (profile) => {
      if (version !== currentSessionVersion()) return;
      queryClient.setQueryData(profileKeys.my(userId), profile);
      queryClient.removeQueries({ queryKey: profileKeys.public(profile.publicId) });
    },
  });
}

export function useCompleteOnboarding() {
  const userId = useAuthStore((state) => state.user?.id);
  const queryClient = useQueryClient();
  const version = useAuthStore((state) => state.sessionVersion);
  return useMutation({
    mutationFn: () => {
      requireCurrentSession(version);
      return completeOnboarding();
    },
    onSuccess: (profile) => {
      if (version !== currentSessionVersion()) return;
      queryClient.setQueryData(profileKeys.my(userId), profile);
      queryClient.removeQueries({ queryKey: profileKeys.public(profile.publicId) });
    },
  });
}

export function usePublicProfile(publicId: string | undefined) {
  return useQuery({
    queryKey: profileKeys.public(publicId ?? ''),
    queryFn: () => getPublicProfile(publicId ?? ''),
    enabled: Boolean(publicId),
    retry: false,
  });
}
