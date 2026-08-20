export const CSRF_COOKIE_NAME = 'unishop_csrf_token';

export function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const match = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));

  if (!match) return null;
  try {
    return decodeURIComponent(match.slice(prefix.length));
  } catch {
    return null;
  }
}

export function readCsrfCookie(): string | null {
  return readCookie(CSRF_COOKIE_NAME);
}
