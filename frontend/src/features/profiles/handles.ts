import { z } from 'zod';

export const reservedHandles = new Set([
  'admin', 'api', 'auth', 'login', 'logout', 'register', 'profile', 'profiles',
  'users', 'seller', 'sellers', 'settings', 'account', 'support', 'help', 'about',
  'search', 'notifications', 'messages', 'chat', 'products', 'categories', 'cities',
  'dev', 'static', 'assets',
]);

export const publicHandleSchema = z.string()
  .regex(/^[a-z0-9][a-z0-9_-]{1,28}[a-z0-9]$/)
  .refine((value) => !reservedHandles.has(value));

export function normalizePublicHandle(value: string): string | null {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) return null;
  const parsed = publicHandleSchema.safeParse(value.toLowerCase());
  return parsed.success ? parsed.data : null;
}

export function publicProfilePath(handle: string): string {
  const normalized = normalizePublicHandle(handle);
  return normalized ? `/u/${normalized}` : '/not-found';
}
