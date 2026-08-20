import { useMutation } from '@tanstack/react-query';
import { login } from './api';
import { logoutAllSessions, logoutCurrentSession } from './session';

export function useLoginMutation() {
  return useMutation({ mutationFn: login });
}

export function useLogoutMutation() {
  return useMutation({ mutationFn: logoutCurrentSession });
}

export function useLogoutAllMutation() {
  return useMutation({ mutationFn: logoutAllSessions });
}
