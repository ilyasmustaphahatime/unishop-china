import type { z } from 'zod';
import type { ownProductImageSchema, publicProductImageSchema } from './schemas';
export type OwnProductImage = z.infer<typeof ownProductImageSchema>;
export type PublicProductImage = z.infer<typeof publicProductImageSchema>;
export type ImageCommand = { action: 'upload'; file: File }
  | { action: 'reorder'; refs: string[] }
  | { action: 'delete'; ref: string };
