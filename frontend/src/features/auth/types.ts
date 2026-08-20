export type UserRole = 'BUYER' | 'SELLER' | 'ADMIN';
export type AccountStatus = 'ACTIVE' | 'SUSPENDED' | 'BANNED' | 'DELETED';
export type AuthStatus = 'bootstrapping' | 'authenticated' | 'unauthenticated';

export type AuthUser = {
  id: string;
  email: string | null;
  phoneNumber: string | null;
  emailVerified: boolean;
  phoneVerified: boolean;
  accountStatus: AccountStatus;
  roles: UserRole[];
  createdAt: string;
};

export type LoginCredentials = {
  identifier: string;
  password: string;
};

export type LoginResponse = {
  accessToken: string;
  tokenType: 'bearer';
  expiresIn: number;
  user: AuthUser;
};

export type RefreshResponse = Omit<LoginResponse, 'user'>;
