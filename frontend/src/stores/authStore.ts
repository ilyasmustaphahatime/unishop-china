import { create } from 'zustand';
import type { AuthUser, LoginResponse, UserRole } from '../features/auth/types';

type AuthState = {
  accessToken: string | null;
  user: AuthUser | null;
  roles: UserRole[];
  isAuthenticated: boolean;
  completeLogin: (session: LoginResponse) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  roles: [],
  isAuthenticated: false,
  completeLogin: ({ accessToken, user }) => {
    set({ accessToken, user, roles: user.roles, isAuthenticated: true });
  },
  logout: () => {
    set({ accessToken: null, user: null, roles: [], isAuthenticated: false });
  },
}));
