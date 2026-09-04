import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import LoginForm from '../../src/components/auth/LoginForm';
import { loginSchema } from '../../src/features/auth/schemas';
import { sessionClient } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const loginResponse = {
  access_token: 'memory-value-a',
  token_type: 'bearer',
  expires_in: 900,
  user: {
    id: 'synthetic-user',
    email: 'synthetic@example.test',
    phone_number: null,
    email_verified: true,
    phone_verified: false,
    account_status: 'ACTIVE',
    roles: ['BUYER'],
    created_at: '2026-01-01T00:00:00Z',
  },
} as const;

function response<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  };
}

function statusError(status: number, detail: string): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('Request failed', AxiosError.ERR_BAD_REQUEST, config, undefined, {
    data: { detail },
    status,
    statusText: 'Request failed',
    headers: new AxiosHeaders(),
    config,
  });
}

function renderLogin(from: unknown = undefined) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname: '/login', state: { from } }]}>
        <Routes>
          <Route path="/login" element={<LoginForm />} />
          <Route path="/messages" element={<p>Messages destination</p>} />
          <Route path="/profile" element={<p>Profile destination</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  useAuthStore.getState().clearSession();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('real login integration', () => {
  it('accepts legacy non-empty passwords without registration strength validation', () => {
    expect(loginSchema.safeParse({ identifier: 'synthetic@example.test', password: 'x' }).success).toBe(
      true,
    );
  });

  it('stores the safe response in memory and follows an intended internal route', async () => {
    const request = vi.spyOn(sessionClient, 'post').mockResolvedValue(response(loginResponse));
    const user = userEvent.setup();
    renderLogin({ pathname: '/messages' });

    await user.type(screen.getByLabelText('Email address or phone number'), 'synthetic@example.test');
    await user.type(screen.getByLabelText('Password'), 'x');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Messages destination')).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith('/auth/login', {
      identifier: 'synthetic@example.test',
      password: 'x',
    });
    expect(sessionClient.defaults.withCredentials).toBe(true);
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: 'memory-value-a',
      status: 'authenticated',
      user: {
        id: 'synthetic-user',
        emailVerified: true,
        phoneVerified: false,
        roles: ['BUYER'],
      },
    });
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });

  it('uses a safe default instead of an external post-login destination', async () => {
    vi.spyOn(sessionClient, 'post').mockResolvedValue(response(loginResponse));
    const user = userEvent.setup();
    renderLogin('//evil.example');

    await user.type(screen.getByLabelText('Email address or phone number'), 'synthetic@example.test');
    await user.type(screen.getByLabelText('Password'), 'x');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Profile destination')).toBeInTheDocument();
  });

  it('does not reveal inactive-account details or establish local state on failure', async () => {
    vi.spyOn(sessionClient, 'post').mockRejectedValue(statusError(403, 'Account suspended.'));
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Email address or phone number'), 'synthetic@example.test');
    await user.type(screen.getByLabelText('Password'), 'wrong-value');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('email, phone number, or password is incorrect');
    expect(alert).not.toHaveTextContent('suspended');
    expect(useAuthStore.getState()).toMatchObject({
      accessToken: null,
      user: null,
      status: 'unauthenticated',
    });
  });
});
