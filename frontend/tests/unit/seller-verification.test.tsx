import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { createElement, type ReactNode } from 'react';
import SellerVerificationPage from '../../src/pages/seller/SellerVerificationPage';
import ProtectedRoute from '../../src/routes/ProtectedRoute';
import { queryClient } from '../../src/app/queryClient';
import { useAuthStore } from '../../src/stores/authStore';
import { clearAuthenticatedSession } from '../../src/services/apiClient';
import * as api from '../../src/features/sellerVerification/api';
import { useVerificationMutation, verificationKey } from '../../src/features/sellerVerification/hooks';
import { validateEvidenceFile, verificationSchema } from '../../src/features/sellerVerification/schemas';
import type { SellerVerification } from '../../src/features/sellerVerification/types';

const user = {
  id: 'synthetic-owner', email: null, phoneNumber: null, accountStatus: 'ACTIVE' as const,
  roles: ['BUYER' as const], emailVerified: true, phoneVerified: true, createdAt: '2026-01-01',
};
const draft: SellerVerification = {
  review_reference: 'a'.repeat(32), status: 'PENDING', handwritten_challenge: 'ABCDEF123456',
  rejection_reason: null, submitted_at: null, reviewed_at: null, created_at: '2026-01-01',
  evidence: [],
};
const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
function page(value: SellerVerification | null = draft, verified = true) {
  useAuthStore.getState().setAuthenticated('synthetic-memory-token', { ...user, emailVerified: verified });
  vi.spyOn(api, 'getVerification').mockResolvedValue(value);
  return render(<QueryClientProvider client={queryClient}><MemoryRouter>
    <SellerVerificationPage /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => { cleanup(); queryClient.clear(); useAuthStore.getState().setBootstrapping(); vi.restoreAllMocks(); });

describe('seller verification page', () => {
  it('loads a private draft and keeps submit disabled without three images', async () => {
    page();
    expect(await screen.findByText('ABCDEF123456')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit for review' })).toBeDisabled();
    expect(screen.getAllByLabelText(/Selfie|WeChat proof|Handwritten code/)).toHaveLength(3);
  });
  it('blocks start for unverified accounts', async () => {
    page(null, false);
    expect(await screen.findByRole('button', { name: 'Start verification' })).toBeDisabled();
  });
  it('starts a draft without sending ownership fields', async () => {
    const change = vi.spyOn(api, 'changeVerification').mockResolvedValue(draft);
    page(null);
    fireEvent.click(await screen.findByRole('button', { name: 'Start verification' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('start'));
    expect(await screen.findByText('ABCDEF123456')).toBeInTheDocument();
  });
  it('uploads a validated image and updates the private response', async () => {
    const upload = vi.spyOn(api, 'uploadEvidence').mockResolvedValue({ ...draft,
      evidence: [{ evidence_type: 'SELFIE', mime_type: 'image/png', size: 10 }] });
    page();
    await screen.findByText('ABCDEF123456');
    const file = new File(['synthetic'], 'proof.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Selfie'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload selfie' }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith('SELFIE', file));
    expect(await screen.findByText('Uploaded')).toBeInTheDocument();
  });
  it('rejects invalid files before calling the API', async () => {
    const upload = vi.spyOn(api, 'uploadEvidence');
    page();
    await screen.findByText('ABCDEF123456');
    fireEvent.change(screen.getByLabelText('Selfie'), { target: { files: [new File(['x'], 'payload.exe')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload selfie' }));
    expect(await screen.findByText('Use a simple JPEG or PNG filename.')).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();
  });
  it.each(['UNDER_REVIEW', 'VERIFIED'] as const)('locks uploads when %s', async (status) => {
    page({ ...draft, status });
    await screen.findByRole('heading', { name: 'Seller verification' });
    expect(screen.queryByLabelText('Selfie')).not.toBeInTheDocument();
  });
  it('renders rejection text safely and allows a fresh attempt', async () => {
    page({ ...draft, status: 'REJECTED', rejection_reason: '<script>not HTML</script>' });
    expect(await screen.findByText('Review feedback: <script>not HTML</script>')).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByRole('button', { name: 'Start verification' })).toBeEnabled();
  });
  it('protects the route against anonymous users', async () => {
    useAuthStore.getState().clearSession();
    render(<MemoryRouter initialEntries={['/seller/verification']}><Routes>
      <Route element={<ProtectedRoute />}><Route path="/seller/verification" element={<p>Private seller data</p>} /></Route>
      <Route path="/login" element={<p>Sign in first</p>} />
    </Routes></MemoryRouter>);
    expect(await screen.findByText('Sign in first')).toBeInTheDocument();
    expect(screen.queryByText('Private seller data')).not.toBeInTheDocument();
  });
});

describe('seller cache and contract security', () => {
  it('uses separate account keys and clears mutation-created private entries', () => {
    expect(verificationKey('a')).not.toEqual(verificationKey('b'));
    queryClient.setQueryData(verificationKey('a'), draft);
    clearAuthenticatedSession();
    expect(queryClient.getQueryData(verificationKey('a'))).toBeUndefined();
  });
  it('does not repopulate cache after a late mutation across logout', async () => {
    useAuthStore.getState().setAuthenticated('synthetic', user);
    let resolve!: (data: SellerVerification) => void;
    vi.spyOn(api, 'changeVerification').mockReturnValue(new Promise((done) => { resolve = done; }));
    const { result } = renderHook(useVerificationMutation, { wrapper });
    let promise!: Promise<SellerVerification>;
    await act(async () => { promise = result.current.mutateAsync({ action: 'start' }); await Promise.resolve(); });
    clearAuthenticatedSession();
    await act(async () => { resolve(draft); await promise; });
    expect(queryClient.getQueryData(verificationKey(user.id))).toBeUndefined();
  });
  it('rejects server payloads exposing private storage fields', () => {
    expect(verificationSchema.safeParse({ ...draft, storage_key: 'private' }).success).toBe(false);
  });
  it.each([
    new File([], 'empty.png', { type: 'image/png' }),
    new File(['x'], '../proof.png', { type: 'image/png' }),
    new File(['x'], 'proof.png', { type: 'image/jpeg' }),
    new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' }),
  ])('rejects an unsafe file', (file) => expect(validateEvidenceFile(file)).not.toBeNull());
});
