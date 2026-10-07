import { z } from 'zod';
import { catalogSlugSchema } from '../catalog/slugs';

export const citySchema = z.object({
  slug: catalogSlugSchema,
  name_en: z.string().min(1).max(80),
  name_zh: z.string().min(1).max(80),
  province_en: z.string().min(1).max(80),
  province_zh: z.string().min(1).max(80).nullable(),
  country_code: z.literal('CN'),
}).strict();
export const cityListSchema = z.object({ items: z.array(citySchema).max(200) }).strict();
