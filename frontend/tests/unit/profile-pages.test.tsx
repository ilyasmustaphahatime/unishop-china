import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import ProfileGate from '../../src/components/profiles/ProfileGate';
import EditProfilePage from '../../src/pages/shared/EditProfilePage';
import OnboardingPage from '../../src/pages/shared/OnboardingPage';
import ProfilePage from '../../src/pages/shared/ProfilePage';
import PublicProfilePage from '../../src/pages/public/PublicProfilePage';
import { profileKeys } from '../../src/features/profiles/hooks';
import type { MyProfile } from '../../src/features/profiles/types';
import { apiClient } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const userId = 'phase6-frontend-user';
const authUser = {
  id: userId,
  email: 'profile@example.test',
  phoneNumber: null,
  emailVerified: true,
  phoneVerified: false,
  accountStatus: 'ACTIVE' as const,
  roles: ['BUYER' as const],
  createdAt: '2026-01-01T00:00:00Z',
};
const incompleteProfile: MyProfile = {
  publicId: '11111111-1111-4111-8111-111111111111',
  displayName: null,
  bio: null,
  city: null,
  onboardingCompleted: false,
  memberSince: '2026-01-01T00:00:00Z',
  createdAt: '2026-09-04T00:00:00Z',
  updatedAt: '2026-09-04T00:00:00Z',
  emailVerified: true,
  phoneVerified: false,
};
const completeProfile: MyProfile = {
  ...incompleteProfile,
  displayName: 'Profile Person',
  bio: null,
  city: 'Qingdao',
  onboardingCompleted: true,
};

function apiProfile(profile: MyProfile) {
  return {
    public_id: profile.publicId,
    display_name: profile.displayName,
    bio: profile.bio,
    city: profile.city,
    onboarding_completed: profile.onboardingCompleted,
    member_since: profile.memberSince,
    created_at: profile.createdAt,
    updated_at: profile.updatedAt,
    email_verified: profile.emailVerified,
    phone_verified: profile.phoneVerified,
  };
}

function response<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  };
}

function renderWithProfile(
  element: React.ReactNode,
  profile: MyProfile | undefined,
  { route = '/profile', children }: { route?: string; children?: React.ReactNode } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (profile) client.setQueryData(profileKeys.my(userId), profile);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="*" element={element} />
          {children}
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  useAuthStore.getState().setBootstrapping();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('onboarding experience', () => {
  it('renders the welcome step and completes saved profile steps', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    let current = incompleteProfile;
    const patch = vi.spyOn(apiClient, 'patch').mockImplementation(async (_url, payload) => {
      const values = payload as { display_name?: string; bio?: string | null; city?: 'Qingdao' };
      current = {
        ...current,
        displayName: values.display_name ?? current.displayName,
        bio: values.bio === undefined ? current.bio : values.bio,
        city: values.city ?? current.city,
      };
      return response(apiProfile(current));
    });
    const post = vi.spyOn(apiClient, 'post').mockImplementation(async () => {
      current = { ...current, onboardingCompleted: true };
      return response(apiProfile(current));
    });
    const user = userEvent.setup();
    renderWithProfile(<OnboardingPage />, incompleteProfile, { route: '/onboarding' });

    expect(screen.getByRole('heading', { name: 'Welcome to UniShop China' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Get started' }));
    await user.type(screen.getByLabelText('Display name'), 'Lin Wei');
    await user.type(screen.getByLabelText('Bio (optional)'), 'Student in China');
    await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    expect(await screen.findByRole('heading', { name: 'Choose your city' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Current city'), 'Qingdao');
    await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    expect(await screen.findByRole('heading', { name: 'Review your profile status' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Finish setup' }));

    expect(await screen.findByRole('heading', { name: 'You are ready' })).toBeInTheDocument();
    expect(patch).toHaveBeenNthCalledWith(1, '/profile/me', {
      display_name: 'Lin Wei',
      bio: 'Student in China',
    });
    expect(patch).toHaveBeenNthCalledWith(2, '/profile/me', { city: 'Qingdao' });
    expect(post).toHaveBeenCalledWith('/profile/onboarding/complete', {});
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });

  it('shows aligned validation before sending an invalid basic profile', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const patch = vi.spyOn(apiClient, 'patch');
    const user = userEvent.setup();
    renderWithProfile(<OnboardingPage />, incompleteProfile, { route: '/onboarding' });
    await user.click(screen.getByRole('button', { name: 'Get started' }));
    await user.type(screen.getByLabelText('Display name'), 'x');
    await user.click(screen.getByRole('button', { name: 'Save and continue' }));

    expect(await screen.findByText('Display name must contain at least 2 characters.')).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
  });

  it('redirects a completed user and resumes a partially saved user at city', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const completed = renderWithProfile(<OnboardingPage />, completeProfile, {
      route: '/onboarding',
      children: <Route path="/profile" element={<p>Profile destination</p>} />,
    });
    expect(await screen.findByText('Profile destination')).toBeInTheDocument();
    completed.unmount();

    renderWithProfile(
      <OnboardingPage />,
      { ...incompleteProfile, displayName: 'Saved Person' },
      { route: '/onboarding' },
    );
    expect(await screen.findByRole('heading', { name: 'Choose your city' })).toBeInTheDocument();
  });
});

describe('profile routing and display', () => {
  it('routes an incomplete authenticated user to onboarding', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const client = new QueryClient();
    client.setQueryData(profileKeys.my(userId), incompleteProfile);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/profile']}>
          <Routes>
            <Route path="/onboarding" element={<p>Onboarding destination</p>} />
            <Route element={<ProfileGate />}>
              <Route path="/profile" element={<p>Private profile</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Onboarding destination')).toBeInTheDocument();
  });

  it('shows a loading state and a safe retry state', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    vi.spyOn(apiClient, 'get').mockReturnValue(new Promise(() => undefined));
    const view = renderWithProfile(<ProfileGate />, undefined);
    expect(screen.getByRole('status')).toHaveTextContent('Loading your profile');
    view.unmount();

    vi.mocked(apiClient.get).mockRejectedValue(new Error('network unavailable'));
    renderWithProfile(<ProfileGate />, undefined);
    expect(await screen.findByRole('alert', {}, { timeout: 4_000 })).toHaveTextContent('unexpected');
  });

  it('shows an empty bio and renders XSS-shaped text without creating HTML', () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const view = renderWithProfile(<ProfilePage />, completeProfile);
    expect(screen.getByText('No bio yet')).toBeInTheDocument();
    view.unmount();

    renderWithProfile(
      <ProfilePage />,
      { ...completeProfile, displayName: '<script>alert(1)</script>', bio: '<img src=x onerror=alert(1)>' },
    );
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('profile editing and public privacy', () => {
  it('loads initial values, blocks invalid submit, and saves once', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue(
      response(apiProfile({ ...completeProfile, displayName: 'Updated Person', bio: 'Updated bio' })),
    );
    const user = userEvent.setup();
    renderWithProfile(<EditProfilePage />, completeProfile, {
      route: '/profile/edit',
      children: <Route path="/profile" element={<p>Saved destination</p>} />,
    });
    const name = screen.getByLabelText('Display name');
    expect(name).toHaveValue('Profile Person');
    await user.clear(name);
    await user.type(name, 'x');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByText('Display name must contain at least 2 characters.')).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();

    await user.clear(name);
    await user.type(name, 'Updated Person');
    await user.type(screen.getByLabelText('Bio (optional)'), 'Updated bio');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByText('Saved destination')).toBeInTheDocument();
    expect(patch).toHaveBeenCalledTimes(1);
  });

  it('maps backend validation errors to a safe message', async () => {
    useAuthStore.getState().setAuthenticated('memory-only-token', authUser);
    const config = { headers: new AxiosHeaders() };
    vi.spyOn(apiClient, 'patch').mockRejectedValue(
      new AxiosError('unsafe backend value', AxiosError.ERR_BAD_REQUEST, config, undefined, {
        data: { detail: 'raw internal details' },
        status: 422,
        statusText: 'Unprocessable',
        headers: new AxiosHeaders(),
        config,
      }),
    );
    const user = userEvent.setup();
    renderWithProfile(<EditProfilePage />, completeProfile, { route: '/profile/edit' });
    await user.click(screen.getByRole('button', { name: 'Save profile' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Check the profile details');
    expect(alert).not.toHaveTextContent('raw internal');
  });

  it('renders only safe public profile fields', async () => {
    const publicResponse = {
      public_id: completeProfile.publicId,
      display_name: 'Public Person',
      bio: '<img src=x onerror=alert(1)>',
      city: 'Shanghai',
      member_since: completeProfile.memberSince,
      email_verified: true,
      phone_verified: false,
    };
    vi.spyOn(apiClient, 'get').mockResolvedValue(response(publicResponse));
    renderWithProfile(<PublicProfilePage />, undefined, {
      route: `/users/${completeProfile.publicId}`,
      children: <Route path="/users/:publicId" element={<PublicProfilePage />} />,
    });
    expect(await screen.findByText('Public Person')).toBeInTheDocument();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(screen.queryByText(authUser.email)).not.toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });
});
