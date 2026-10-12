import { createElement, type ReactNode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/app/queryClient';
import { clearAuthenticatedSession } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';
import { productKeys, useProductMutation } from '../../src/features/products/hooks';
import * as api from '../../src/features/products/api';
import type { OwnProduct } from '../../src/features/products/types';
import { apiClient } from '../../src/services/apiClient';
import { AxiosHeaders, type AxiosResponse } from 'axios';

afterEach(() => { queryClient.clear(); vi.restoreAllMocks(); useAuthStore.getState().setBootstrapping(); localStorage.clear(); sessionStorage.clear(); });
function signIn(id: string) {
  useAuthStore.getState().setAuthenticated('memory-token', { id, email: null, phoneNumber: null, accountStatus: 'ACTIVE',
    roles: ['BUYER'], emailVerified: true, phoneVerified: true, createdAt: '2026-01-01T00:00:00Z' });
}
it('private listing keys are partitioned by identity AND session version', () => {
  expect(productKeys.mine('a', 1)).not.toEqual(productKeys.mine('b', 1));
  expect(productKeys.mine('a', 1)).not.toEqual(productKeys.mine('a', 2));
});
it('logout clears owner listing cache without persisting draft or bearer data', async () => {
  signIn('a');
  const key = productKeys.mine('a', useAuthStore.getState().sessionVersion);
  await queryClient.fetchQuery({ queryKey: key, meta: { private: true }, queryFn: async () => ({ description: 'PRIVATE DRAFT' }) });
  clearAuthenticatedSession();
  expect(queryClient.getQueryData(key)).toBeUndefined();
  expect(useAuthStore.getState().accessToken).toBeNull();
  expect(localStorage).toHaveLength(0);
  expect(sessionStorage).toHaveLength(0);
});
it.each(['logout', 'account-switch'])('late private mutation cannot restore previous cache after %s', async (change) => {
  signIn('a');
  const version = useAuthStore.getState().sessionVersion;
  let resolve!: (p: OwnProduct) => void;
  vi.spyOn(api, 'transitionProduct').mockReturnValue(new Promise<OwnProduct>((done) => { resolve = done; }));
  const { result } = renderHook(useProductMutation, { wrapper: ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children) });
  let pending!: Promise<OwnProduct>;
  await act(async () => { pending = result.current.mutateAsync({ action: 'archive', slug: 'item-' + 'a'.repeat(24) }); await Promise.resolve(); });
  if (change === 'logout') clearAuthenticatedSession(); else signIn('b');
  await act(async () => { resolve({ public_slug: 'item-' + 'a'.repeat(24) } as OwnProduct); await pending; });
  expect(queryClient.getQueryData(productKeys.own('a', version, 'item-' + 'a'.repeat(24)))).toBeUndefined();
});

it.each(['logout', 'account-switch'])('rejects late owner API response after %s before parsing or caching', async (change) => {
  signIn('a');
  let resolve!: (response: AxiosResponse) => void;
  vi.spyOn(apiClient, 'get').mockReturnValue(new Promise<AxiosResponse>((done) => { resolve = done; }));
  const pending = api.getMyProduct('item-' + 'a'.repeat(24));
  const rejected = expect(pending).rejects.toThrow('Session changed.');
  if (change === 'logout') clearAuthenticatedSession(); else signIn('b');
  resolve({ data: { description: 'PRIVATE OLD DRAFT' }, status: 200, statusText: 'OK',
    config: { headers: new AxiosHeaders() }, headers: new AxiosHeaders() });
  await rejected;
});
