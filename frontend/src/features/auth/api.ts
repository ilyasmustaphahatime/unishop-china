import { apiClient, sessionClient } from '../../services/apiClient';
import type { AuthUser, LoginCredentials, LoginResponse } from './types';
import {
  authUserApiSchema,
  loginApiSchema,
  type AuthUserApiResponse,
} from './contracts';

function mapUser(user: AuthUserApiResponse): AuthUser {
  return {
    id: user.id,
    email: user.email,
    phoneNumber: user.phone_number,
    emailVerified: user.email_verified,
    phoneVerified: user.phone_verified,
    accountStatus: user.account_status,
    roles: user.roles,
    createdAt: user.created_at,
  };
}

export async function login(credentials: LoginCredentials): Promise<LoginResponse> {
  const response = await sessionClient.post('/auth/login', credentials);
  const data = loginApiSchema.parse(response.data);

  return {
    accessToken: data.access_token,
    tokenType: data.token_type,
    expiresIn: data.expires_in,
    user: mapUser(data.user),
  };
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await apiClient.get('/auth/me');
  return mapUser(authUserApiSchema.parse(response.data));
}
