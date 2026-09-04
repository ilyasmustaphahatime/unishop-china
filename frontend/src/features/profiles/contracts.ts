import { z } from 'zod';
import { supportedCities } from './types';

const baseProfileFields = {
  public_id: z.uuid(),
  display_name: z.string().nullable(),
  bio: z.string().nullable(),
  city: z.enum(supportedCities).nullable(),
  member_since: z.string().min(1),
  email_verified: z.boolean(),
  phone_verified: z.boolean(),
};

export const myProfileApiSchema = z
  .object({
    ...baseProfileFields,
    onboarding_completed: z.boolean(),
    created_at: z.string().min(1),
    updated_at: z.string().min(1),
  })
  .strict();

export const publicProfileApiSchema = z
  .object({
    ...baseProfileFields,
    display_name: z.string(),
    city: z.enum(supportedCities),
  })
  .strict();
