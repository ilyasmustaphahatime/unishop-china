import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { normalizePublicHandle, publicProfilePath, reservedHandles } from '../../src/features/profiles/handles';
import { publicProfileApiSchema } from '../../src/features/profiles/contracts';
import { localFakeSmsApi } from '../../src/features/auth/localFakeSmsApi';
import { apiClient } from '../../src/services/apiClient';
import { safeInternalPath } from '../../src/routes/routePaths';
import PublicProfilePage from '../../src/pages/public/PublicProfilePage';

afterEach(() => vi.restoreAllMocks());

describe('public handle navigation policy', () => {
  it.each(['abc', 'a'.repeat(30), 'user-k7m4', 'a_b'])('normalizes safe handle %s', (handle) => {
    expect(normalizePublicHandle(handle.toUpperCase())).toBe(handle);
    expect(publicProfilePath(handle)).toBe(`/u/${handle}`);
  });

  it.each([
    '', 'a', 'ab', 'a'.repeat(31), ' abc', 'abc ', 'a b', 'user/abc', 'user\\abc',
    '../admin', 'a..b', '%2Fadmin', '%252Fadmin', 'ab\n', 'a\tb', 'a\u202eb',
    '\u0430bc', '\u212aey', '😀abc', '<script>', 'javascript:', 'abc_', '-abc',
    '550e8400-e29b-41d4-a716-446655440000', ...reservedHandles,
  ])('rejects unsafe handle %j', (handle) => {
    expect(normalizePublicHandle(handle)).toBeNull();
    expect(publicProfilePath(handle)).toBe('/not-found');
  });

  it.each([
    '/profile?token=synthetic', '/profile?code=123456', '/profile#otp=123456',
    '/profile?csrf=synthetic', '/profile?session=synthetic', '/profile?email=private',
    '/profile?phone=private', '/users/42', '/users/550e8400-e29b-41d4-a716-446655440000',
    'https://evil.example', '//evil.example', '/\\evil.example', '/%2F%2Fevil.example',
    '/%5cevil.example', 'javascript:alert(1)', 'data:text/html,x', '/profile/../admin',
    '/u/user-ok?code=123456', '/u/user-ok#token', '/u/%75ser-ok', '/profile\n',
  ])('never propagates unsafe redirect %j', (path) => {
    expect(safeInternalPath(path, '/profile')).toBe('/profile');
  });

  it('drops location-object query/hash and rejects unsafe fallback', () => {
    expect(safeInternalPath({ pathname: '/u/USER-OK', search: '?token=x', hash: '#code=x' }, '/'))
      .toBe('/u/user-ok');
    expect(safeInternalPath(null, '//evil.example')).toBe('/');
  });

  it('rejects the legacy UUID response field', () => {
    expect(publicProfileApiSchema.safeParse({ public_id: crypto.randomUUID() }).success).toBe(false);
  });
});

function publicPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/u/user-k7m4']}>
        <Routes><Route path="/u/:handle" element={<PublicProfilePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it('loads a public handle directly and after a fresh mount without private state', async () => {
  const request = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: {
    public_handle: 'user-k7m4', display_name: 'Public Person', bio: null, city: 'Qingdao',
    member_since: '2026-01-01', email_verified: false, phone_verified: false,
  } });
  const first = publicPage();
  expect(await screen.findByText('Public Person')).toBeInTheDocument();
  first.unmount();
  publicPage();
  expect(await screen.findByText('Public Person')).toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(2);
  expect(request).toHaveBeenLastCalledWith('/profiles/by-handle/user-k7m4');
});

it.each(['unknown', 'incomplete', 'suspended', 'banned', 'deleted'])(
  'uses the same unavailable view for %s profiles', async () => {
    const config = { headers: new AxiosHeaders() };
    vi.spyOn(apiClient, 'get').mockRejectedValue(new AxiosError('Unavailable', undefined, config,
      undefined, { status: 404, statusText: 'Not found', data: { detail: 'Profile not found.' },
        headers: new AxiosHeaders(), config }));
    publicPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('This profile is not available.');
  },
);

it('sends development lookup identifiers and message references only in JSON bodies', async () => {
  const post = vi.spyOn(apiClient, 'post').mockRejectedValue(new Error('controlled'));
  const signal = new AbortController().signal;
  await expect(localFakeSmsApi.latest('+8613800000000', signal)).rejects.toThrow();
  await localFakeSmsApi.consume('synthetic-message-reference');
  expect(post).toHaveBeenNthCalledWith(1, '/dev/fake-sms/latest',
    { phone_number: '+8613800000000' }, { signal });
  expect(post).toHaveBeenNthCalledWith(2, '/dev/fake-sms/consume',
    { message_id: 'synthetic-message-reference' });
  expect(post.mock.calls.every(([url]) => !/[?#]/.test(url))).toBe(true);
});
