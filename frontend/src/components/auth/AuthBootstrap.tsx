import { useEffect, type PropsWithChildren } from 'react';
import { bootstrapSession } from '../../features/auth/session';

export default function AuthBootstrap({ children }: PropsWithChildren) {
  useEffect(() => {
    void bootstrapSession();
  }, []);

  return children;
}
