import { create } from 'zustand';
import type { AuthStatus, AuthUser } from '../features/auth/types';

export type AuthState = {
  accessToken: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  sessionVersion: number;
  setAccessToken: (accessToken: string) => void;
  setAuthenticated: (accessToken: string, user: AuthUser) => void;
  setBootstrapping: () => void;
  clearSession: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: 'bootstrapping',
  sessionVersion: 0,
  setAccessToken: (accessToken) => set({ accessToken }),
  setAuthenticated: (accessToken, user) =>
    set((state) => ({ accessToken, user, status: 'authenticated', sessionVersion: state.sessionVersion + 1 })),
  setBootstrapping: () => set((state) => ({ accessToken: null, user: null, status: 'bootstrapping', sessionVersion: state.sessionVersion + 1 })),
  clearSession: () => set((state) => ({ accessToken: null, user: null, status: 'unauthenticated', sessionVersion: state.sessionVersion + 1 })),
}));
