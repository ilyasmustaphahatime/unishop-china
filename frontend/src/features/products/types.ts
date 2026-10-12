import type { z } from 'zod';
import type { productInputSchema, ownProductSchema, publicProductSchema } from './schemas';
export type ProductInput = z.infer<typeof productInputSchema>;
export type OwnProduct = z.infer<typeof ownProductSchema>;
export type PublicProduct = z.infer<typeof publicProductSchema>;
export type ProductAction = 'publish' | 'pause' | 'archive';
