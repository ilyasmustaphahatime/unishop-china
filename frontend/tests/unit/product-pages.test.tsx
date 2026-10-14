import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import AddProductPage from '../../src/pages/seller/AddProductPage';
import EditProductPage from '../../src/pages/seller/EditProductPage';
import SellerProductsPage from '../../src/pages/seller/SellerProductsPage';
import ProductDetailsPage from '../../src/pages/public/ProductDetailsPage';
import { apiClient } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';
import type { OwnProduct } from '../../src/features/products/types';
import { productKeys } from '../../src/features/products/hooks';
import { formatListingTimestamp } from '../../src/i18n/formatters';

const slug = 'item-' + 'a'.repeat(24);
const city = { slug: 'qingdao', name_en: 'Qingdao', name_zh: '青岛', province_en: 'Shandong', province_zh: '山东', country_code: 'CN' as const };
const category = { slug: 'study', name_en: 'Study', name_zh: '学习', description: null, parent_slug: null };
const product: OwnProduct = {
  public_slug: slug, title: 'Study desk', description: '<script>PRIVATE DRAFT</script>', price: '123.45',
  currency: 'CNY', condition: 'good', city, category, published_at: null,
  status: 'DRAFT', city_active: true, category_active: true,
  created_at: '2026-10-08T00:00:00Z', updated_at: '2026-10-08T00:00:00Z',
};
function response<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() } };
}
function renderPage(page: React.ReactNode, route = '/seller/listings') {
  useAuthStore.getState().setAuthenticated('memory-only-test-token', {
    id: 'product-frontend-owner', email: null, phoneNumber: null, accountStatus: 'ACTIVE', roles: ['BUYER'],
    emailVerified: true, phoneVerified: true, createdAt: product.created_at,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const rendered = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}>
    <Routes><Route path="/sell/new" element={page} /><Route path="/seller/listings" element={page} />
      <Route path="/seller/listings/:slug/edit" element={page} /><Route path="/p/:slug" element={page} /></Routes>
  </MemoryRouter></QueryClientProvider>);
  return { ...rendered, client };
}
function mockCatalogs(listing = product) {
  return vi.spyOn(apiClient, 'get').mockImplementation(async (path) => {
    if (path === '/cities') return response({ items: [city] });
    if (path === '/categories') return response({ items: [{ ...category, children: [] }] });
    if (String(path).endsWith('/images')) return response([]);
    return response(listing);
  });
}
afterEach(() => { vi.restoreAllMocks(); useAuthStore.getState().setBootstrapping(); });

it('creates draft using string price and server catalog slugs only', async () => {
  mockCatalogs();
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue(response(product));
  const user = userEvent.setup();
  renderPage(<AddProductPage />, '/sell/new');
  await user.type(screen.getByLabelText('Title'), 'Study desk');
  await user.type(screen.getByLabelText('Description'), 'A sturdy desk in good condition.');
  await user.type(screen.getByLabelText('Price (CNY)'), '123.45');
  await screen.findByRole('option', { name: 'Study' });
  await user.selectOptions(screen.getByLabelText('City'), 'qingdao');
  await user.selectOptions(screen.getByLabelText('Category'), 'study');
  await user.click(screen.getByRole('button', { name: 'Create draft' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/seller/products', {
    title: 'Study desk', description: 'A sturdy desk in good condition.', price: '123.45',
    condition: 'good', city_slug: 'qingdao', category_slug: 'study',
  }));
});
it('owner list links use only opaque slugs and displays all states', async () => {
  const items = ['DRAFT', 'PUBLISHED', 'PAUSED', 'ARCHIVED'].map((status, index) => ({
    ...product, public_slug: 'item-' + String(index).repeat(24), status,
  }));
  vi.spyOn(apiClient, 'get').mockResolvedValue(response({ items, next_offset: null }));
  renderPage(<SellerProductsPage />);
  expect(await screen.findByText('ARCHIVED')).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'Study desk' })).toHaveLength(4);
  expect(screen.getAllByRole('link', { name: 'Study desk' })[0]).toHaveAttribute('href', '/seller/listings/item-' + '0'.repeat(24) + '/edit');
});
it('owner list includes the listing condition and last-updated time', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue(response({ items: [product], next_offset: null }));
  const view = renderPage(<SellerProductsPage />);
  await screen.findByRole('link', { name: 'Study desk' });
  expect(screen.getByText(/Condition: Good/)).toBeInTheDocument();
  expect(view.container.querySelector('time')).toHaveAttribute('dateTime', product.updated_at);
  expect(view.container.querySelector('time')).toHaveTextContent(formatListingTimestamp(product.updated_at));
  expect(view.container.querySelector('time')).toHaveTextContent('UTC');
});
it('rapid repeated form submissions issue only one draft request while delivery is pending', async () => {
  mockCatalogs();
  const resolvers: Array<(value: AxiosResponse<OwnProduct>) => void> = [];
  const post = vi.spyOn(apiClient, 'post').mockImplementation(() => new Promise((resolve) => { resolvers.push(resolve); }));
  const user = userEvent.setup();
  const view = renderPage(<AddProductPage />, '/sell/new');
  await user.type(screen.getByLabelText('Title'), 'Study desk');
  await user.type(screen.getByLabelText('Description'), 'A sturdy desk in good condition.');
  await user.type(screen.getByLabelText('Price (CNY)'), '123.45');
  await screen.findByRole('option', { name: 'Study' });
  await user.selectOptions(screen.getByLabelText('City'), 'qingdao');
  await user.selectOptions(screen.getByLabelText('Category'), 'study');
  try {
    await act(async () => {
      const form = view.container.querySelector('form')!;
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledTimes(1);
  } finally {
    await act(async () => { for (const resolve of resolvers) resolve(response(product)); });
  }
});
it('a failed draft request releases the submission guard for an explicit retry', async () => {
  mockCatalogs();
  const post = vi.spyOn(apiClient, 'post').mockRejectedValueOnce(new Error('SYNTHETIC PRIVATE FAILURE'))
    .mockResolvedValueOnce(response(product));
  const user = userEvent.setup();
  renderPage(<AddProductPage />, '/sell/new');
  await user.type(screen.getByLabelText('Title'), 'Study desk');
  await user.type(screen.getByLabelText('Description'), 'A sturdy desk in good condition.');
  await user.type(screen.getByLabelText('Price (CNY)'), '123.45');
  await screen.findByRole('option', { name: 'Study' });
  await user.selectOptions(screen.getByLabelText('City'), 'qingdao');
  await user.selectOptions(screen.getByLabelText('Category'), 'study');
  await user.click(screen.getByRole('button', { name: 'Create draft' }));
  expect(await screen.findByRole('alert')).not.toHaveTextContent('SYNTHETIC PRIVATE FAILURE');
  await user.click(screen.getByRole('button', { name: 'Create draft' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
});
it('public HTML-shaped content is rendered as text, not HTML', async () => {
  const { city_active: _, category_active: __, created_at: ___, updated_at: ____, ...fields } = product;
  void [_ , __, ___, ____];
  vi.spyOn(apiClient, 'get').mockResolvedValue(response({ ...fields, status: 'PUBLISHED',
    published_at: product.created_at, seller: { public_handle: 'user-publicseller', display_name: '<img src=x>', seller_verified: true } }));
  const rendered = renderPage(<ProductDetailsPage />, '/p/' + slug);
  expect(await screen.findByText('<script>PRIVATE DRAFT</script>')).toBeInTheDocument();
  expect(rendered.container.querySelector('script')).toBeNull();
  expect(rendered.container.querySelector('img')).toBeNull();
  expect(screen.getByRole('link', { name: '<img src=x>' })).toHaveAttribute('href', '/u/user-publicseller');
});
it('invalid public reference never makes an API request', () => {
  const get = vi.spyOn(apiClient, 'get');
  renderPage(<ProductDetailsPage />, '/p/not-an-item');
  expect(screen.getByRole('alert')).toHaveTextContent('not available');
  expect(get).not.toHaveBeenCalled();
});
it('archived owner detail is read-only with no lifecycle action buttons', async () => {
  mockCatalogs({ ...product, status: 'ARCHIVED' });
  renderPage(<EditProductPage />, '/seller/listings/' + slug + '/edit');
  expect(await screen.findByText('Archived listings are read-only.')).toBeInTheDocument();
  expect(screen.getByLabelText('Title')).toBeDisabled();
  for (const name of ['Publish', 'Pause', 'Archive permanently', 'Save changes']) expect(screen.queryByRole('button', { name })).toBeNull();
});
it('patch sends only changed fields, preserving retired assignments', async () => {
  mockCatalogs({ ...product, city_active: false, category_active: false });
  const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue(response({ ...product, title: 'New title' }));
  const user = userEvent.setup();
  renderPage(<EditProductPage />, '/seller/listings/' + slug + '/edit');
  const title = await screen.findByLabelText('Title');
  await user.clear(title);
  await user.type(title, 'New title');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(patch).toHaveBeenCalledWith('/seller/products/' + slug, { title: 'New title' }));
});
it('lifecycle button posts an empty body, not a forged status', async () => {
  mockCatalogs();
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue(response({ ...product, status: 'PUBLISHED', published_at: product.created_at }));
  renderPage(<EditProductPage />, '/seller/listings/' + slug + '/edit');
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Publish' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/seller/products/' + slug + '/publish', {}));
});
it('catalog failure exposes retry and never invents fallback choices', async () => {
  vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('PRIVATE DRIVER ERROR'));
  renderPage(<AddProductPage />, '/sell/new');
  expect(await screen.findByText('Retry categories', {}, { timeout: 3000 })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /Study/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Create draft' })).toBeDisabled();
  expect(screen.queryByText('PRIVATE DRIVER ERROR')).toBeNull();
});

it('hides previously visible public data when a refetch returns not found', async () => {
  const { city_active: _, category_active: __, created_at: ___, updated_at: ____, ...fields } = product;
  void [_, __, ___, ____];
  const get = vi.spyOn(apiClient, 'get').mockResolvedValue(response({ ...fields, status: 'PUBLISHED',
    published_at: product.created_at, seller: { public_handle: 'user-seller123', display_name: 'Seller', seller_verified: true } }));
  const view = renderPage(<ProductDetailsPage />, '/p/' + slug);
  await screen.findByText('<script>PRIVATE DRAFT</script>');
  const error = new AxiosError('Hidden listing');
  error.response = { ...response({ detail: 'Listing not found.' }), status: 404 };
  get.mockRejectedValue(error);
  await view.client.invalidateQueries({ queryKey: productKeys.public(slug) });
  expect(await screen.findByRole('alert')).toHaveTextContent('This listing is not available.');
  expect(screen.queryByText('<script>PRIVATE DRAFT</script>')).toBeNull();
});
