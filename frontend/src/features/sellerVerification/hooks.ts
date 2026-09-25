import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import { getVerification, changeVerification, uploadEvidence } from './api';
import type { EvidenceType } from './types';

export const verificationKey = (userId: string | undefined) => ['seller-verification', 'me', userId] as const;

export function useVerification() {
  const userId = useAuthStore((s) => s.user?.id);
  const authenticated = useAuthStore((s) => s.status === 'authenticated');
  return useQuery({
    queryKey: verificationKey(userId), queryFn: getVerification,
    enabled: authenticated && Boolean(userId), meta: { private: true },
    staleTime: 0, retry: false,
  });
}

type Command = { action: 'start' | 'submit' } | { action: 'upload'; kind: EvidenceType; file: File };
export function useVerificationMutation() {
  const userId = useAuthStore((s) => s.user?.id);
  const version = useAuthStore((s) => s.sessionVersion);
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (command: Command) => {
      requireCurrentSession(version);
      return command.action === 'upload'
        ? uploadEvidence(command.kind, command.file) : changeVerification(command.action);
    },
    onSuccess: (data) => {
      if (version !== currentSessionVersion()) return;
      client.setQueryData(verificationKey(userId), data);
    },
    gcTime: 0,
  });
}
