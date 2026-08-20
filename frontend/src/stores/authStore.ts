import { create } from 'zustand';
import type { AuthStatus, AuthUser } from '../features/auth/types';

export type AuthState = {
  accessToken: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  setAccessToken: (accessToken: string) => void;
  setAuthenticated: (accessToken: string, user: AuthUser) => void;
  setBootstrapping: () => void;
  clearSession: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: 'bootstrapping',
  setAccessToken: (accessToken) => set({ accessToken }),
  setAuthenticated: (accessToken, user) =>
    set({ accessToken, user, status: 'authenticated' }),
  setBootstrapping: () => set({ accessToken: null, user: null, status: 'bootstrapping' }),
  clearSession: () => set({ accessToken: null, user: null, status: 'unauthenticated' }),
}));
