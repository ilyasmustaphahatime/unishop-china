import { z } from 'zod';
import { citySchema } from '../cities/schemas';
import { categorySchema } from '../categories/schemas';
import { catalogSlugSchema } from '../catalog/slugs';
import { publicHandleSchema } from '../profiles/handles';

export const productSlugSchema = z.string().regex(/^item-[0-9a-f]{24}$/);
export const conditionSchema = z.enum(['new', 'like_new', 'good', 'fair']);
export const statusSchema = z.enum(['DRAFT', 'PUBLISHED', 'PAUSED', 'ARCHIVED']);
const priceInput = z.string().regex(/^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/, 'Enter a positive CNY price with at most two decimal places.')
  .refine((value) => !/^0(?:\.0{1,2})?$/.test(value), 'Price must be positive.');
const priceOutput = z.string().regex(/^(?:0|[1-9][0-9]{0,9})\.[0-9]{2}$/).refine((p) => p !== '0.00');

function plainText(minimum: number, maximum: number, multiline = false) {
  return z.string().transform((s) => s.normalize('NFC').replace(/\r\n/g, '\n').trim())
    .refine((s) => Array.from(s).length >= minimum && Array.from(s).length <= maximum, `Use ${minimum}–${maximum} characters.`)
    .refine((s) => !Array.from(s).some((c) => {
      const code = c.codePointAt(0) ?? 0;
      return ((code < 32 || (code >= 127 && code <= 159)) && !(multiline && (c === '\n' || c === '\t')))
        || (code >= 0xd800 && code <= 0xdfff)
        || [0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069].includes(code);
    }), 'Unsupported control characters.');
}

export const productInputSchema = z.object({
  title: plainText(3, 120).transform((s) => s.replace(/\s+/g, ' ')),
  description: plainText(10, 5000, true),
  price: priceInput,
  condition: conditionSchema,
  city_slug: catalogSlugSchema,
  category_slug: catalogSlugSchema,
}).strict();

const productFields = {
  public_slug: productSlugSchema,
  title: z.string().min(3).max(240),
  description: z.string().min(10).max(10000),
  price: priceOutput,
  currency: z.literal('CNY'),
  condition: conditionSchema,
  city: citySchema,
  category: categorySchema,
  published_at: z.string().nullable(),
};
export const ownProductSchema = z.object({
  ...productFields, status: statusSchema, city_active: z.boolean(), category_active: z.boolean(),
  created_at: z.string(), updated_at: z.string(),
}).strict();
export const ownProductListSchema = z.object({
  items: z.array(ownProductSchema).max(100), next_offset: z.number().int().nonnegative().nullable(),
}).strict();
export const publicProductSchema = z.object({
  ...productFields, status: z.literal('PUBLISHED'),
  seller: z.object({ public_handle: publicHandleSchema, display_name: z.string().min(2).max(100),
    seller_verified: z.literal(true) }).strict(),
}).strict();
