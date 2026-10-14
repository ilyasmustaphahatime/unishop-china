import type { ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import LanguageSwitcher from '../../src/components/layout/LanguageSwitcher';
import MainLayout from '../../src/components/layout/MainLayout';
import AuthLayout from '../../src/components/layout/AuthLayout';
import AuthenticatedLayout from '../../src/components/layout/AuthenticatedLayout';
import LoginForm from '../../src/components/auth/LoginForm';
import Avatar from '../../src/components/common/Avatar';
import ProductForm from '../../src/components/products/ProductForm';
import ProductImageManager from '../../src/components/products/ProductImageManager';
import OwnerProductImage from '../../src/components/products/OwnerProductImage';
import ProductStatusBadge from '../../src/components/products/ProductStatusBadge';
import ProfileForm from '../../src/components/profiles/ProfileForm';
import ProductDetailsPage from '../../src/pages/public/ProductDetailsPage';
import SellerVerificationPage from '../../src/pages/seller/SellerVerificationPage';
import * as verificationApi from '../../src/features/sellerVerification/api';
import type { OwnProduct } from '../../src/features/products/types';
import type { MyProfile } from '../../src/features/profiles/types';
import { apiClient, clearAuthenticatedSession, sessionClient } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';
import { queryClient } from '../../src/app/queryClient';
import { i18n } from '../../src/i18n';
import { languages, supportedLanguages } from '../../src/i18n/languages';
import { resources } from '../../src/i18n/resources';
import { localePreferenceKey } from '../../src/i18n/persistence';
import { formatCurrency } from '../../src/i18n/formatters';

const slug = 'item-' + 'a'.repeat(24), ref = 'img-' + 'a'.repeat(32);
const city = { slug: 'qingdao', name_en: 'Qingdao', name_zh: '青岛', province_en: 'Shandong', province_zh: '山东', country_code: 'CN' as const };
const category = { slug: 'study', name_en: 'Study', name_zh: '学习', description: null, parent_slug: null };
const product: OwnProduct = {
  public_slug: slug, title: 'Desk مكتب 书桌', description: 'Original seller description وصف أصلي.',
  price: '123.45', currency: 'CNY', condition: 'good', city, category, published_at: null,
  status: 'DRAFT', city_active: true, category_active: true,
  created_at: '2026-10-08T00:00:00Z', updated_at: '2026-10-08T00:00:00Z',
};
function response<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() } };
}
function signIn(id = 'seller-a') {
  useAuthStore.getState().setAuthenticated('synthetic-memory-only', {
    id, email: null, phoneNumber: null, accountStatus: 'ACTIVE', roles: ['BUYER'],
    emailVerified: true, phoneVerified: true, createdAt: product.created_at,
  });
}
function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search + location.hash}</output>;
}
function mount(children: ReactNode) {
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/sell/new?keep=yes#anchor']}>
    <LanguageSwitcher /><Location />{children}
  </MemoryRouter></QueryClientProvider>);
}
async function switchTo(locale: typeof supportedLanguages[number]) {
  await userEvent.selectOptions(screen.getByRole('combobox', { name: i18n.t('common:language') }), locale);
  await waitFor(() => expect(document.documentElement.lang).toBe(locale));
}
afterEach(() => { cleanup(); queryClient.clear(); useAuthStore.getState().setBootstrapping(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('global locale UI', () => {
  it('escapes malicious interpolation in translated accessibility labels', async () => {
    mount(<Avatar name={'<img src=x onerror=alert(1)> مستخدم'} />);
    await switchTo('ar');
    expect(screen.getByRole('img')).toHaveAccessibleName(resources.ar.common.avatar.replace('{{name}}', '<img src=x onerror=alert(1)> مستخدم'));
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
  });
  it.each([MainLayout, AuthLayout, AuthenticatedLayout])('provides a semantic switcher in every implemented global shell', (Layout) => {
    useAuthStore.getState().clearSession();
    render(<QueryClientProvider client={queryClient}><MemoryRouter><Layout /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole('combobox', { name: 'Language' })).toBeInTheDocument();
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['English', '简体中文', 'العربية', 'Français']);
  });
  it.each(supportedLanguages)('updates selected locale, document direction and metadata: %s', async (locale) => {
    mount(<ProductStatusBadge status="PUBLISHED" />);
    await switchTo(locale);
    expect(screen.getByRole('combobox', { name: resources[locale].common.language })).toHaveValue(locale);
    expect(document.documentElement.dir).toBe(languages[locale].direction);
    expect(document.title).toBe(resources[locale].common.documentTitle);
    expect(screen.getByText(resources[locale].products.published)).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/sell/new?keep=yes#anchor');
  });
  it('is focusable using Tab and exposes native language names/labels', async () => {
    mount(null);
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole('combobox', { name: 'Language' })).toHaveFocus();
    expect(screen.getByRole('option', { name: 'العربية' })).toHaveAttribute('lang', 'ar');
    await user.selectOptions(screen.getByRole('combobox'), 'ar');
    expect(screen.getByRole('combobox')).toHaveFocus();
  });
  it('does not show a stale failure while a newer language choice is pending', async () => {
    let failFirst!: (reason?: unknown) => void;
    let finishLatest!: () => void;
    const first = new Promise<void>((_resolve, reject) => { failFirst = reject; });
    const latest = new Promise<void>((resolve) => { finishLatest = resolve; });
    const original = i18n.changeLanguage.bind(i18n);
    const change = vi.spyOn(i18n, 'changeLanguage').mockImplementation(async (value) => {
      if (value === 'ar') await first;
      if (value === 'fr') await latest;
      return original(value);
    });
    try {
      mount(null);
      const selector = screen.getByRole('combobox', { name: 'Language' });
      fireEvent.change(selector, { target: { value: 'ar' } });
      await waitFor(() => expect(change).toHaveBeenCalledWith('ar'));
      fireEvent.change(selector, { target: { value: 'fr' } });
      failFirst(new Error('synthetic locale failure'));
      await waitFor(() => expect(change).toHaveBeenCalledWith('fr'));
      expect(screen.queryByRole('alert')).toBeNull();
      finishLatest();
      await waitFor(() => expect(document.documentElement.lang).toBe('fr'));
      expect(screen.queryByRole('alert')).toBeNull();
      expect(localStorage.getItem(localePreferenceKey)).toBe('fr');
    } finally {
      change.mockRestore();
    }
  });
  it('preserves typed login credentials and re-localizes an existing validation error', async () => {
    const post = vi.spyOn(apiClient, 'post');
    const sessionPost = vi.spyOn(sessionClient, 'post');
    const user = userEvent.setup();
    mount(<LoginForm />);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Enter your email address or phone number.')).toBeInTheDocument();
    await switchTo('ar');
    expect(screen.getByText(resources.ar.validation.identifierRequired)).toBeInTheDocument();
    const identifier = screen.getByLabelText(resources.ar.auth.identifier);
    const password = screen.getByLabelText(resources.ar.auth.password);
    await user.type(identifier, 'synthetic@example.test');
    await user.type(password, 'OnlySynthetic123');
    await switchTo('fr');
    expect(screen.getByLabelText(resources.fr.auth.identifier)).toBe(identifier);
    expect(identifier).toHaveValue('synthetic@example.test');
    expect(password).toHaveValue('OnlySynthetic123');
    expect(identifier).toHaveAttribute('dir', 'ltr');
    expect(password).toHaveAttribute('dir', 'ltr');
    expect(post).not.toHaveBeenCalled();
    expect(sessionPost).not.toHaveBeenCalled();
  });
});

describe('forms, sessions and media stay independent of locale', () => {
  it('preserves unsaved profile edits across language switches without sending a patch', async () => {
    signIn();
    const profile: MyProfile = {
      publicHandle: 'user-a1b2c3d4', displayName: 'Original Name', bio: 'Original bio',
      city: 'Qingdao', citySlug: city.slug, cityActive: true, onboardingCompleted: true,
      memberSince: product.created_at, createdAt: product.created_at, updatedAt: product.updated_at,
      emailVerified: true, phoneVerified: true,
    };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(response({ items: [city] }));
    const patch = vi.spyOn(apiClient, 'patch');
    const user = userEvent.setup();
    mount(<ProfileForm profile={profile} />);
    const name = screen.getByLabelText('Display name'), bio = screen.getByLabelText('Bio (optional)');
    await user.clear(name); await user.type(name, 'Updated Name');
    await user.clear(bio); await user.type(bio, 'Unsaved profile details');
    const initialRequests = get.mock.calls.length;
    for (const locale of ['ar', 'fr', 'zh-CN', 'en'] as const) {
      await switchTo(locale);
      expect(screen.getByLabelText(resources[locale].profile.displayName)).toBe(name);
      expect(name).toHaveValue('Updated Name');
      expect(bio).toHaveValue('Unsaved profile details');
      expect(screen.getByLabelText(resources[locale].catalog.city)).toHaveValue(city.slug);
      expect(get).toHaveBeenCalledTimes(initialRequests);
      expect(patch).not.toHaveBeenCalled();
    }
  });
  it('preserves an existing product edit and sends only changed fields after a locale switch', async () => {
    signIn();
    vi.spyOn(apiClient, 'get').mockImplementation(async (path) => response(path === '/cities' ? { items: [city] } : { items: [{ ...category, children: [] }] }));
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue(response(product));
    const user = userEvent.setup();
    mount(<ProductForm product={product} />);
    const title = screen.getByLabelText('Title');
    await user.clear(title); await user.type(title, 'Edited multilingual desk');
    await switchTo('ar'); await switchTo('fr');
    expect(screen.getByLabelText(resources.fr.products.title)).toBe(title);
    expect(title).toHaveValue('Edited multilingual desk');
    expect(screen.getByLabelText(resources.fr.products.price)).toHaveValue('123.45');
    expect(screen.getByLabelText(resources.fr.catalog.city)).toHaveValue(city.slug);
    expect(screen.getByLabelText(resources.fr.catalog.category)).toHaveValue(category.slug);
    expect(patch).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: resources.fr.products.saveChanges }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/seller/products/' + slug, { title: 'Edited multilingual desk' }));
  });
  it('preserves unsaved product values, selects, focus and exact decimal/enum payload across locales', async () => {
    signIn();
    const get = vi.spyOn(apiClient, 'get').mockImplementation(async (path) => response(path === '/cities' ? { items: [city] } : { items: [{ ...category, children: [] }] }));
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue(response(product));
    const user = userEvent.setup();
    mount(<ProductForm />);
    await screen.findByRole('option', { name: 'Study' });
    const title = screen.getByLabelText('Title'), description = screen.getByLabelText('Description'), price = screen.getByLabelText('Price (CNY)');
    await user.type(title, product.title);
    await user.type(description, product.description);
    await user.type(price, product.price);
    await user.selectOptions(screen.getByLabelText('City'), city.slug);
    await user.selectOptions(screen.getByLabelText('Category'), category.slug);
    const initialRequests = get.mock.calls.length;
    for (const locale of ['ar', 'fr', 'zh-CN', 'en'] as const) {
      await switchTo(locale);
      expect(screen.getByLabelText(resources[locale].products.title)).toBe(title);
      expect(title).toHaveValue(product.title);
      expect(description).toHaveValue(product.description);
      expect(price).toHaveValue('123.45');
      expect(price).toHaveAttribute('dir', 'ltr');
      expect(screen.getByLabelText(resources[locale].catalog.city)).toHaveValue(city.slug);
      expect(screen.getByLabelText(resources[locale].catalog.category)).toHaveValue(category.slug);
      expect(get).toHaveBeenCalledTimes(initialRequests);
      expect(post).not.toHaveBeenCalled();
    }
    await user.click(screen.getByRole('button', { name: 'Create draft' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/seller/products', {
      title: product.title, description: product.description, price: '123.45', condition: 'good', city_slug: city.slug, category_slug: category.slug,
    }));
  });
  it('preserves memory auth, private caches and cookies without auth network calls; logout clears private data but not locale', async () => {
    signIn();
    queryClient.setQueryDefaults(['private-test'], { meta: { private: true } });
    queryClient.setQueryData(['private-test'], { owner: 'seller-a' });
    const initial = useAuthStore.getState();
    const privateValue = queryClient.getQueryData(['private-test']);
    const request = vi.spyOn(apiClient, 'request'), sessionPost = vi.spyOn(sessionClient, 'post');
    const cookies = document.cookie;
    mount(null);
    await switchTo('ar');
    expect(useAuthStore.getState().accessToken).toBe(initial.accessToken);
    expect(useAuthStore.getState().user).toBe(initial.user);
    expect(useAuthStore.getState().sessionVersion).toBe(initial.sessionVersion);
    expect(queryClient.getQueryData(['private-test'])).toBe(privateValue);
    expect(document.cookie).toBe(cookies);
    expect(request).not.toHaveBeenCalled();
    expect(sessionPost).not.toHaveBeenCalled();
    expect(Object.keys(localStorage)).toEqual([localePreferenceKey]);
    await act(async () => clearAuthenticatedSession());
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(queryClient.getQueryData(['private-test'])).toBeUndefined();
    expect(localStorage.getItem(localePreferenceKey)).toBe('ar');
    await act(async () => signIn('seller-b'));
    expect(i18n.resolvedLanguage).toBe('ar');
    expect(queryClient.getQueryData(['private-test'])).toBeUndefined();
  });
  it('does not refetch/recreate private Blob previews; logout revokes them and a second account cannot reuse them', async () => {
    signIn();
    const nativeURL = URL, create = vi.fn(() => 'blob:synthetic-i18n'), revoke = vi.fn();
    class TestURL extends nativeURL { static createObjectURL = create; static revokeObjectURL = revoke; }
    vi.stubGlobal('URL', TestURL);
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(response(new Blob(['synthetic-png'], { type: 'image/png' })));
    mount(<OwnerProductImage slug={slug} imageRef={ref} position={0} />);
    const image = await screen.findByRole('img');
    await waitFor(() => expect(image).toHaveAttribute('src', 'blob:synthetic-i18n'));
    for (const locale of ['fr', 'zh-CN', 'ar'] as const) await switchTo(locale);
    expect(screen.getByRole('img')).toBe(image);
    expect(create).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledTimes(1);
    expect(revoke).not.toHaveBeenCalled();
    expect(localStorage.getItem(localePreferenceKey)).toBe('ar');
    expect(JSON.stringify(localStorage)).not.toContain('blob:');
    await act(async () => clearAuthenticatedSession());
    expect(screen.queryByRole('img')).toBeNull();
    expect(revoke).toHaveBeenCalledWith('blob:synthetic-i18n');
    get.mockImplementation(() => new Promise(() => {}));
    await act(async () => signIn('seller-b'));
    expect(screen.queryByRole('img')).toBeNull();
    expect(create).toHaveBeenCalledTimes(1);
    expect(i18n.resolvedLanguage).toBe('ar');
  });
  it('rejects Seller A image bytes that arrive after Arabic is retained by Seller B', async () => {
    signIn('seller-a');
    const create = vi.fn(() => 'blob:stale-owner-image');
    const nativeURL = URL;
    class TestURL extends nativeURL { static createObjectURL = create; static revokeObjectURL = vi.fn(); }
    vi.stubGlobal('URL', TestURL);
    let deliverA!: (value: AxiosResponse<Blob>) => void;
    const heldA = new Promise<AxiosResponse<Blob>>((resolve) => { deliverA = resolve; });
    const get = vi.spyOn(apiClient, 'get').mockImplementationOnce(() => heldA)
      .mockImplementation(() => new Promise(() => {}));
    mount(<OwnerProductImage slug={slug} imageRef={ref} position={0} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await switchTo('ar');
    await act(async () => {
      clearAuthenticatedSession();
      signIn('seller-b');
    });
    await act(async () => { deliverA(response(new Blob(['Seller A image bytes'], { type: 'image/png' }))); });
    expect(i18n.resolvedLanguage).toBe('ar');
    expect(localStorage.getItem(localePreferenceKey)).toBe('ar');
    expect(create).not.toHaveBeenCalled();
    expect(screen.queryByRole('img')).toBeNull();
    expect(queryClient.getQueryCache().findAll({ queryKey: ['product-images', 'mine', 'seller-a'] })).toHaveLength(0);
  });
  it('keeps a selected product image and does not mutate anything on language change', async () => {
    signIn();
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(response([]));
    const post = vi.spyOn(apiClient, 'post'), patch = vi.spyOn(apiClient, 'patch'), remove = vi.spyOn(apiClient, 'delete');
    mount(<ProductImageManager product={product} />);
    await screen.findByText(/No images yet/);
    const file = new File(['png'], 'synthetic.png', { type: 'image/png' });
    const input = screen.getByLabelText('Add image');
    fireEvent.change(input, { target: { files: [file] } });
    await switchTo('ar');
    expect(screen.getByLabelText(resources.ar.products.addImage)).toBe(input);
    expect((input as HTMLInputElement).files?.[0]).toBe(file);
    expect(screen.getByRole('button', { name: resources.ar.products.uploadImage })).toBeEnabled();
    expect(get).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled(); expect(patch).not.toHaveBeenCalled(); expect(remove).not.toHaveBeenCalled();
  });
  it('preserves seller verification challenge and selected evidence without renewing or submitting', async () => {
    signIn();
    const get = vi.spyOn(verificationApi, 'getVerification').mockResolvedValue({
      review_reference: 'a'.repeat(32), status: 'PENDING', handwritten_challenge: 'ABCDEF123456', challenge_expires_at: '2099-01-01T00:00:00Z',
      rejection_reason: null, submitted_at: null, reviewed_at: null, created_at: '2026-01-01', evidence: [],
    });
    const change = vi.spyOn(verificationApi, 'changeVerification'), upload = vi.spyOn(verificationApi, 'uploadEvidence');
    mount(<SellerVerificationPage />);
    await screen.findByText('ABCDEF123456');
    const input = screen.getByLabelText('Handwritten code'), file = new File(['png'], 'synthetic.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    await switchTo('ar'); await switchTo('fr');
    expect(screen.getByText('ABCDEF123456')).toHaveAttribute('dir', 'ltr');
    expect(screen.getByLabelText(resources.fr.verification.handwrittenCode)).toBe(input);
    expect((input as HTMLInputElement).files?.[0]).toBe(file);
    expect(get).toHaveBeenCalledTimes(1); expect(change).not.toHaveBeenCalled(); expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: resources.fr.verification.submit })).toBeDisabled();
  });
  it.each(supportedLanguages)('preserves escaped mixed-script seller content and formats public CNY safely: %s', async (locale) => {
    const { city_active: _, category_active: __, created_at: ___, updated_at: ____, ...fields } = product;
    void [_, __, ___, ____];
    vi.spyOn(apiClient, 'get').mockResolvedValue(response({ ...fields, title: '<img src=x onerror=alert(1)> مكتب', status: 'PUBLISHED',
      seller: { public_handle: 'user-publicseller', display_name: 'Seller البائع', seller_verified: true } }));
    render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/p/' + slug]}>
      <LanguageSwitcher /><Routes><Route path="/p/:slug" element={<ProductDetailsPage />} /></Routes>
    </MemoryRouter></QueryClientProvider>);
    await switchTo(locale);
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('<img src=x onerror=alert(1)> مكتب');
    expect(heading).toHaveAttribute('dir', 'auto');
    expect(document.querySelector('img')).toBeNull(); expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText(product.description)).toHaveAttribute('dir', 'auto');
    expect(screen.getByText((_, element) => element?.tagName === 'BDI' && element.textContent === formatCurrency('123.45', locale)).tagName).toBe('BDI');
    expect(screen.getByRole('link', { name: 'Seller البائع' })).toHaveAttribute('href', '/u/user-publicseller');
  });
});
