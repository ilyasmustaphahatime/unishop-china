import axios from 'axios';
import { apiClient, currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import { ownProductListSchema, ownProductSchema, productInputSchema, productSlugSchema, publicProductSchema } from './schemas';
import type { ProductAction, ProductInput } from './types';

const path = (slug: string) => '/seller/products/' + productSlugSchema.parse(slug);
export async function getMyProducts(offset = 0) {
  const version = currentSessionVersion();
  const response = await apiClient.get('/seller/products', { params: { limit: 20, offset } });
  requireCurrentSession(version);
  return ownProductListSchema.parse(response.data);
}
export async function getMyProduct(slug: string) {
  const version = currentSessionVersion();
  const response = await apiClient.get(path(slug));
  requireCurrentSession(version);
  return ownProductSchema.parse(response.data);
}
export async function createProduct(input: ProductInput) {
  const version = currentSessionVersion();
  const response = await apiClient.post('/seller/products', productInputSchema.parse(input));
  requireCurrentSession(version);
  return ownProductSchema.parse(response.data);
}
export async function updateProduct(slug: string, input: Partial<ProductInput>) {
  const version = currentSessionVersion();
  const parsed = productInputSchema.partial().strict().parse(input);
  if (!Object.keys(parsed).length) throw new Error('No listing changes.');
  const response = await apiClient.patch(path(slug), parsed);
  requireCurrentSession(version);
  return ownProductSchema.parse(response.data);
}
export async function transitionProduct(slug: string, action: ProductAction) {
  const version = currentSessionVersion();
  const response = await apiClient.post(path(slug) + '/' + action, {});
  requireCurrentSession(version);
  return ownProductSchema.parse(response.data);
}
export async function getPublicProduct(slug: string) {
  const response = await apiClient.get('/products/' + productSlugSchema.parse(slug));
  return publicProductSchema.parse(response.data);
}
export function productErrorMessage(error: unknown) {
  if (!axios.isAxiosError(error)) return 'The listing request could not be completed. Please try again.';
  if (!error.response) return 'Unable to reach UniShop China. Check your connection.';
  const messages: Record<number, string> = {
    401: 'Your session ended. Please sign in again.',
    403: 'Complete onboarding and verify email, phone, and seller identity before creating, editing, or publishing.',
    404: 'This listing is not available.',
    409: 'This action is no longer available. Refresh the listing to see its current state.',
    422: 'Check your listing details and choose active catalog entries.',
    429: 'Too many listing requests. Wait a moment before trying again.',
    503: 'Listings are temporarily unavailable. Please try again later.',
  };
  return messages[error.response.status] ?? 'The listing request could not be completed. Please try again.';
}
