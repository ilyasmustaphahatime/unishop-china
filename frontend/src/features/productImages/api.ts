import axios from 'axios';
import { apiClient, currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import { productSlugSchema } from '../products/schemas';
import { IMAGE_LIMITS, IMAGE_MIME_TYPES, imageRefSchema, ownProductImageListSchema, ownProductImageSchema, validateUpload } from './schemas';

const path = (slug: string) => '/seller/products/' + productSlugSchema.parse(slug) + '/images';
function parseList(data: unknown, slug: string) {
  const images = ownProductImageListSchema.parse(data);
  if (images.some((image) => !image.url.endsWith('/seller/products/' + slug + '/images/' + image.ref))) {
    throw new Error('Invalid image metadata.');
  }
  return images;
}
export async function getMyProductImages(slug: string) {
  const version = currentSessionVersion();
  const response = await apiClient.get(path(slug));
  requireCurrentSession(version);
  return parseList(response.data, slug);
}
export async function uploadProductImage(slug: string, file: File) {
  const error = validateUpload(file);
  if (error) throw new Error(error);
  const version = currentSessionVersion();
  const form = new FormData();
  form.append('file', file, 'product-image'); // Do not send the user's personal filename.
  const response = await apiClient.post(path(slug), form, { headers: { 'Content-Type': undefined } });
  requireCurrentSession(version);
  const image = ownProductImageSchema.parse(response.data);
  if (!image.url.endsWith('/seller/products/' + slug + '/images/' + image.ref)) throw new Error('Invalid image metadata.');
  return image;
}
export async function reorderProductImages(slug: string, refs: string[]) {
  if (refs.length > IMAGE_LIMITS.count || new Set(refs).size !== refs.length) throw new Error('Invalid image order.');
  const parsed = refs.map((ref) => imageRefSchema.parse(ref));
  const version = currentSessionVersion();
  const response = await apiClient.patch(path(slug) + '/order', { images: parsed });
  requireCurrentSession(version);
  return parseList(response.data, slug);
}
export async function deleteProductImage(slug: string, ref: string) {
  const version = currentSessionVersion();
  await apiClient.delete(path(slug) + '/' + imageRefSchema.parse(ref));
  requireCurrentSession(version);
}
export async function getOwnerImageBlob(slug: string, ref: string) {
  const version = currentSessionVersion();
  const response = await apiClient.get<Blob>(path(slug) + '/' + imageRefSchema.parse(ref), { responseType: 'blob' });
  requireCurrentSession(version);
  const blob = response.data;
  if (!(blob instanceof Blob) || blob.size <= 0 || blob.size > IMAGE_LIMITS.bytes ||
      !IMAGE_MIME_TYPES.some((type) => type === blob.type)) throw new Error('Image preview unavailable.');
  return blob;
}
export function publicImageUrl(slug: string, ref: string) {
  const route = 'products/' + productSlugSchema.parse(slug) + '/images/' + imageRefSchema.parse(ref);
  const base = new URL(apiClient.defaults.baseURL ?? '/api/v1', window.location.origin);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new Error('Invalid API location.');
  }
  return new URL(route, base.href.replace(/\/$/, '') + '/').href;
}
export function imageErrorMessage(error: unknown) {
  if (!axios.isAxiosError(error)) return 'The image request could not be completed. Please try again.';
  const messages: Record<number, string> = {
    401: 'Your session ended. Please sign in again.',
    403: 'Current seller approval, verification and onboarding are required to upload or reorder.',
    404: 'This image or listing is not available.',
    409: 'The image set or listing state changed. Refresh and try again.',
    413: 'The image request is too large. Maximum image size is 10 MiB.',
    415: 'Choose a JPEG, PNG or static WebP image.',
    422: 'Choose a safe static image within the format, size and dimension limits.',
    429: 'Too many image requests. Wait before trying again.',
    503: 'Image storage is temporarily unavailable.',
  };
  return error.response ? messages[error.response.status] ?? 'The image request could not be completed.' : 'Unable to reach image storage.';
}
