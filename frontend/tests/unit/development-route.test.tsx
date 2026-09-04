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

describe('Phase 6 route inventory', () => {
  it('exposes profile routes without future marketplace feature routes', () => {
    const paths = collectPaths(
      buildRouteObjects({ isDevelopment: false, fakeSmsPageEnabled: false }),
    );

    expect(paths).toEqual(expect.arrayContaining(['/onboarding', '/profile', '/profile/edit', '/users/:publicId']));
    expect(paths).not.toEqual(
      expect.arrayContaining([
        '/seller/verification',
        '/seller/products',
        '/messages',
        '/admin',
        '/products/:productId',
      ]),
    );
  });
});
