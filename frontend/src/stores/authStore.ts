import { create } from 'zustand';
import type { AuthUser, LoginResponse, UserRole } from '../features/auth/types';
import { tokenStorage, userStorage } from '../services/tokenStorage';

type AuthState = {
  accessToken: string | null;
  user: AuthUser | null;
  roles: UserRole[];
  isAuthenticated: boolean;
  completeLogin: (session: LoginResponse) => void;
  logout: () => void;
};

const storedToken = tokenStorage.get();
const storedUser = userStorage.get();

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: storedToken,
  user: storedUser,
  roles: storedUser?.roles ?? [],
  isAuthenticated: Boolean(storedToken && storedUser),
  completeLogin: ({ accessToken, user }) => {
    tokenStorage.set(accessToken);
    userStorage.set(user);
    set({ accessToken, user, roles: user.roles, isAuthenticated: true });
  },
  logout: () => {
    tokenStorage.clear();
    userStorage.clear();
    set({ accessToken: null, user: null, roles: [], isAuthenticated: false });
  },
}));
