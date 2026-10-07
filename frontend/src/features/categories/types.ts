import type { z } from 'zod';
import type { categoryTreeSchema } from './schemas';
export type CategoryTree = z.infer<typeof categoryTreeSchema>;
