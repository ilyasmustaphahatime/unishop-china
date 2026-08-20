import { z } from 'zod';

export const authUserApiSchema = z
  .object({
    id: z.string().min(1),
    email: z.string().email().nullable(),
    phone_number: z.string().nullable(),
    email_verified: z.boolean(),
    phone_verified: z.boolean(),
    account_status: z.enum(['ACTIVE', 'SUSPENDED', 'BANNED', 'DELETED']),
    roles: z.array(z.enum(['BUYER', 'SELLER', 'ADMIN'])),
    created_at: z.string().min(1),
  })
  .strict();

export const refreshApiSchema = z
  .object({
    access_token: z.string().min(1),
    token_type: z.literal('bearer'),
    expires_in: z.number().int().positive(),
  })
  .strict();

export const loginApiSchema = refreshApiSchema
  .extend({ user: authUserApiSchema })
  .strict();

export type AuthUserApiResponse = z.infer<typeof authUserApiSchema>;
