import { useMutation } from '@tanstack/react-query';
import { login } from './api';

export function useLoginMutation() {
  return useMutation({ mutationFn: login });
}
