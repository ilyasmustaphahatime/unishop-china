import type { UserRole } from '../features/auth/types';

export function dashboardForRoles(roles: UserRole[]): string {
  void roles;
  return '/profile';
}

export function safeInternalPath(candidate: unknown, fallback: string): string {
  let path: string | null = null;
  if (typeof candidate === 'string') {
    path = candidate;
  } else if (candidate && typeof candidate === 'object') {
    const location = candidate as { pathname?: unknown; search?: unknown; hash?: unknown };
    if (typeof location.pathname === 'string') {
      path = `${location.pathname}${typeof location.search === 'string' ? location.search : ''}${
        typeof location.hash === 'string' ? location.hash : ''
      }`;
    }
  }

  if (!path?.startsWith('/') || path.startsWith('//') || path.includes('\\')) return fallback;
  try {
    const parsed = new URL(path, window.location.origin);
    if (parsed.origin !== window.location.origin) return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}
