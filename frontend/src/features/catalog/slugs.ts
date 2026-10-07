import { z } from 'zod';
import { reservedHandles } from '../profiles/handles';

const reserved = new Set([...reservedHandles, 'city', 'category']);
export const catalogSlugSchema = z.string().min(2).max(63)
  .regex(/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/)
  .refine((value) => !reserved.has(value), 'Invalid catalog slug.');
