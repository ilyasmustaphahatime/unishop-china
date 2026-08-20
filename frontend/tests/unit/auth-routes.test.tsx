import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import ProtectedRoute from '../../src/routes/ProtectedRoute';
import GuestRoute from '../../src/routes/GuestRoute';
import { safeInternalPath } from '../../src/routes/routePaths';
import type { AuthUser } from '../../src/features/auth/types';
import { useAuthStore } from '../../src/stores/authStore';

const safeUser: AuthUser = {
  id: 'synthetic-user',
  email: null,
  phoneNumber: '+8613800000000',
  emailVerified: false,
  phoneVerified: true,
  accountStatus: 'ACTIVE',
  roles: ['BUYER'],
  createdAt: '2026-01-01T00:00:00Z',
};

afterEach(() => useAuthStore.getState().setBootstrapping());

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/private']}>
      <Routes>
        <Route path="/login" element={<p>Login page</p>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/private" element={<p>Private page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function renderGuest() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/buyer/dashboard" element={<p>Buyer dashboard</p>} />
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<p>Guest login</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('authentication route guards', () => {
  it('holds a protected route while bootstrapping', () => {
    renderProtected();
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session');
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
  });

  it('renders protected content for an authenticated user', () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    renderProtected();
    expect(screen.getByText('Private page')).toBeInTheDocument();
  });

  it('redirects an unauthenticated user to login', () => {
    useAuthStore.getState().clearSession();
    renderProtected();
    expect(screen.getByText('Login page')).toBeInTheDocument();
  });

  it('holds guest routes while bootstrapping and then renders for a guest', () => {
    const view = renderGuest();
    expect(screen.getByRole('status')).toBeInTheDocument();
    view.unmount();
    useAuthStore.getState().clearSession();
    renderGuest();
    expect(screen.getByText('Guest login')).toBeInTheDocument();
  });

  it('redirects an authenticated visitor away from the login route', () => {
    useAuthStore.getState().setAuthenticated('memory-value-a', safeUser);
    renderGuest();
    expect(screen.getByText('Buyer dashboard')).toBeInTheDocument();
  });
});

describe('safe internal redirects', () => {
  it('preserves internal path, query, and fragment', () => {
    expect(
      safeInternalPath({ pathname: '/messages', search: '?thread=1', hash: '#latest' }, '/'),
    ).toBe('/messages?thread=1#latest');
  });

  it.each(['https://evil.example', '//evil.example', 'javascript:alert(1)', 'data:text/html,x', '/\\evil.example'])(
    'rejects unsafe destination %s',
    (candidate) => expect(safeInternalPath(candidate, '/buyer/dashboard')).toBe('/buyer/dashboard'),
  );
});
