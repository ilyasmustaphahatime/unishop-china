import { apiClient } from '../../services/apiClient';
import type { LoginCredentials, LoginResponse } from './types';

type LoginApiResponse = {
  access_token: string;
  token_type: 'bearer';
  user: {
    id: string;
    display_name: string;
    roles: LoginResponse['user']['roles'];
  };
};

export async function login(credentials: LoginCredentials): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginApiResponse>('/auth/login', credentials);

  return {
    accessToken: data.access_token,
    tokenType: data.token_type,
    user: {
      id: data.user.id,
      displayName: data.user.display_name,
      roles: data.user.roles,
    },
  };
}
