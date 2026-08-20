import type { PropsWithChildren } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import AuthBootstrap from '../components/auth/AuthBootstrap';
import { queryClient } from './queryClient';
export default function Providers({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthBootstrap>{children}</AuthBootstrap>
    </QueryClientProvider>
  );
}
