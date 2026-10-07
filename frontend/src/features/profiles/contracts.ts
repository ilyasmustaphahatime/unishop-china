import { z } from 'zod';
import { publicHandleSchema } from './handles';
import { catalogSlugSchema } from '../catalog/slugs';

const baseProfileFields = {
  public_handle: publicHandleSchema,
  display_name: z.string().nullable(),
  bio: z.string().nullable(),
  city: z.string().min(1).max(80).nullable(),
  member_since: z.string().min(1),
  email_verified: z.boolean(),
  phone_verified: z.boolean(),
};

export const myProfileApiSchema = z
  .object({
    ...baseProfileFields,
    city_slug: catalogSlugSchema.nullable(),
    city_active: z.boolean(),
    onboarding_completed: z.boolean(),
    created_at: z.string().min(1),
    updated_at: z.string().min(1),
  })
  .strict();

export const publicProfileApiSchema = z
  .object({
    ...baseProfileFields,
    display_name: z.string(),
    city: z.string().min(1).max(80),
    seller_verified: z.boolean(),
  })
  .strict();
