import type { z } from 'zod';
import type { citySchema } from './schemas';
export type City = z.infer<typeof citySchema>;
