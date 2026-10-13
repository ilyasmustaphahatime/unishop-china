import { z } from 'zod';

export const IMAGE_LIMITS = { count: 8, bytes: 10 * 1024 * 1024, dimension: 6000, pixels: 30_000_000 } as const;
export const IMAGE_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
export const imageRefSchema = z.string().length(36).regex(/^img-[0-9a-f]{32}$/);
const imageUrl = z.string().max(300).regex(/^\/(?:[A-Za-z0-9_-]+\/)*products\/item-[0-9a-f]{24}\/images\/img-[0-9a-f]{32}$/)
  .refine((value) => !/[\r\n]/.test(value));
const fields = { ref: imageRefSchema, position: z.number().int().min(0).max(7), url: imageUrl };
export const publicProductImageSchema = z.object(fields).strict()
  .refine((image) => !image.url.includes('/seller/') && image.url.endsWith('/' + image.ref));
export const ownProductImageSchema = z.object({
  ...fields, mime_type: z.enum(IMAGE_MIME_TYPES), width: z.number().int().min(1).max(6000),
  height: z.number().int().min(1).max(6000), file_size: z.number().int().min(1).max(IMAGE_LIMITS.bytes),
  created_at: z.string().min(1),
}).strict().refine((image) => image.width * image.height <= IMAGE_LIMITS.pixels &&
  image.url.includes('/seller/products/') && image.url.endsWith('/' + image.ref));
export const ownProductImageListSchema = z.array(ownProductImageSchema).max(IMAGE_LIMITS.count)
  .refine((images) => images.every((image, index) => image.position === index) &&
    new Set(images.map((image) => image.ref)).size === images.length);
export const publicProductImageListSchema = z.array(publicProductImageSchema).max(IMAGE_LIMITS.count)
  .refine((images) => images.every((image, index) => image.position === index) &&
    new Set(images.map((image) => image.ref)).size === images.length);
export function validateUpload(file: File): string | null {
  if (!IMAGE_MIME_TYPES.some((type) => type === file.type)) return 'Choose a JPEG, PNG or static WebP image.';
  if (file.size <= 0 || file.size > IMAGE_LIMITS.bytes) return 'Choose an image between 1 byte and 10 MiB.';
  return null; // UX only: signature, animation, dimensions and metadata checked by server.
}
