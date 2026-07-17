export type UserRole = 'BUYER' | 'SELLER' | 'ADMIN';

export type AuthUser = {
  id: string;
  displayName: string;
  roles: UserRole[];
};

export type LoginCredentials = {
  identifier: string;
  password: string;
};

export type LoginResponse = {
  accessToken: string;
  tokenType: 'bearer';
  user: AuthUser;
};
