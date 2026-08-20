import { z } from 'zod';

export const loginSchema = z.object({
  identifier: z
    .string()
    .trim()
    .min(1, 'Enter your email address or phone number.')
    .max(254, 'Email address or phone number is too long.'),
  password: z
    .string()
    .min(1, 'Enter your password.')
    .max(128, 'Password must contain no more than 128 characters.'),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
