import type { AuthUser } from '../features/auth/types';

const ACCESS_TOKEN_KEY = 'unishopChina.accessToken';
const USER_KEY = 'unishopChina.user';

function readUser(): AuthUser | null {
  const value = localStorage.getItem(USER_KEY);
  if (!value) return null;

  try {
    return JSON.parse(value) as AuthUser;
  } catch {
    localStorage.removeItem(USER_KEY);
    return null;
  }
}

export const tokenStorage = {
  get: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  set: (value: string) => localStorage.setItem(ACCESS_TOKEN_KEY, value),
  clear: () => localStorage.removeItem(ACCESS_TOKEN_KEY),
};

export const userStorage = {
  get: readUser,
  set: (user: AuthUser) => localStorage.setItem(USER_KEY, JSON.stringify(user)),
  clear: () => localStorage.removeItem(USER_KEY),
};
