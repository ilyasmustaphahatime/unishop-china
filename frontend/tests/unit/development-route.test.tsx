import type { RouteObject } from 'react-router';
import { describe, expect, it } from 'vitest';
import { buildRouteObjects } from '../../src/app/router';

function collectPaths(routes: RouteObject[]): string[] {
  return routes.flatMap((route) => [
    ...(route.path ? [route.path] : []),
    ...collectPaths(route.children ?? []),
  ]);
}

describe('development-only fake SMS route', () => {
  it('is present only when development mode and the explicit flag are enabled', () => {
    const paths = collectPaths(
      buildRouteObjects({ isDevelopment: true, fakeSmsPageEnabled: true }),
    );

    expect(paths).toContain('/dev/phone-verification');
  });

  it('is absent from a production route build even when the flag is set', () => {
    const paths = collectPaths(
      buildRouteObjects({ isDevelopment: false, fakeSmsPageEnabled: true }),
    );

    expect(paths).not.toContain('/dev/phone-verification');
  });

  it('is absent when the explicit feature flag is disabled', () => {
    const paths = collectPaths(
      buildRouteObjects({ isDevelopment: true, fakeSmsPageEnabled: false }),
    );

    expect(paths).not.toContain('/dev/phone-verification');
  });
});

describe('Phase 9 route inventory', () => {
  it('exposes profiles and listing core without future marketplace features', () => {
    const paths = collectPaths(
      buildRouteObjects({ isDevelopment: false, fakeSmsPageEnabled: false }),
    );

    expect(paths).toEqual(expect.arrayContaining(['/onboarding', '/profile', '/profile/edit', '/u/:handle']));
    expect(paths).not.toContain('/users/:publicId');
    expect(paths.filter((path) => path.includes(':'))).toEqual(['/u/:handle', '/p/:slug', '/seller/listings/:slug/edit']);
    expect(paths).toEqual(expect.arrayContaining(['/sell/new', '/seller/listings']));
    expect(paths).not.toEqual(
      expect.arrayContaining([
        '/seller/products',
        '/messages',
        '/admin',
        '/products/:productId',
      ]),
    );
  });
});
