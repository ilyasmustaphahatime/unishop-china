import type { UserRole } from '../features/auth/types';
import { normalizePublicHandle } from '../features/profiles/handles';

export function dashboardForRoles(roles: UserRole[]): string {
  void roles;
  return '/profile';
}

const navigationPaths = new Set([
  '/', '/profile', '/profile/edit', '/onboarding', '/login', '/sign-up',
  '/verify-phone', '/forgot-password', '/reset-password', '/safety', '/terms', '/privacy',
  '/seller/verification',
]);

function allowedPath(value: unknown): string | null {
  const path = typeof value === 'string' ? value
    : value && typeof value === 'object' ? (value as { pathname?: unknown }).pathname : null;
  if (typeof path !== 'string') return null;
  // No query/fragment is used by current routes. Never forward arbitrary URL state.
  if (navigationPaths.has(path)) return path;
  if (path.startsWith('/u/')) {
    const handle = normalizePublicHandle(path.slice(3));
    if (handle) return `/u/${handle}`;
  }
  return null;
}

export function safeInternalPath(candidate: unknown, fallback: string): string {
  return allowedPath(candidate) ?? allowedPath(fallback) ?? '/';
}
