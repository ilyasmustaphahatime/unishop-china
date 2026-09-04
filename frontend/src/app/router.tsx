import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter, type RouteObject } from 'react-router';
import AuthLayout from '../components/layout/AuthLayout';
import AuthenticatedLayout from '../components/layout/AuthenticatedLayout';
import MainLayout from '../components/layout/MainLayout';
import ProfileGate from '../components/profiles/ProfileGate';
import GuestRoute from '../routes/GuestRoute';
import ProtectedRoute from '../routes/ProtectedRoute';

const pages = import.meta.glob([
  '../pages/public/HomePage.tsx',
  '../pages/public/PublicProfilePage.tsx',
  '../pages/public/SafetyPage.tsx',
  '../pages/public/TermsPage.tsx',
  '../pages/public/PrivacyPage.tsx',
  '../pages/public/NotFoundPage.tsx',
  '../pages/auth/LoginPage.tsx',
  '../pages/auth/SignUpPage.tsx',
  '../pages/auth/PhoneVerificationPage.tsx',
  '../pages/auth/ForgotPasswordPage.tsx',
  '../pages/auth/ResetPasswordPage.tsx',
  '../pages/shared/OnboardingPage.tsx',
  '../pages/shared/ProfilePage.tsx',
  '../pages/shared/EditProfilePage.tsx',
]);
const localPhoneVerificationPage = import.meta.env.DEV
  ? () => import('../pages/dev/LocalPhoneVerificationPage')
  : undefined;
const localPhoneVerificationPath = import.meta.env.DEV ? '/dev/phone-verification' : undefined;

function page(path: string) {
  const Page = lazy(pages[`../pages/${path}.tsx`] as () => Promise<{ default: ComponentType }>);
  return (
    <Suspense fallback={<p className="p-6 text-slate-600">Loading…</p>}>
      <Page />
    </Suspense>
  );
}

function developmentPage() {
  if (!localPhoneVerificationPage) return null;
  const Page = lazy(localPhoneVerificationPage);
  return (
    <Suspense fallback={<p className="p-6 text-slate-600">Loadingâ€¦</p>}>
      <Page />
    </Suspense>
  );
}

function mapRoutes(routes: Array<[string, string]>): RouteObject[] {
  return routes.map(([path, component]) => ({ path, element: page(component) }));
}

const publicRoutes = mapRoutes([
  ['/', 'public/HomePage'],
  ['/users/:publicId', 'public/PublicProfilePage'],
  ['/safety', 'public/SafetyPage'],
  ['/terms', 'public/TermsPage'],
  ['/privacy', 'public/PrivacyPage'],
]);
const guestRoutes = mapRoutes([
  ['/login', 'auth/LoginPage'],
  ['/sign-up', 'auth/SignUpPage'],
  ['/verify-phone', 'auth/PhoneVerificationPage'],
  ['/forgot-password', 'auth/ForgotPasswordPage'],
  ['/reset-password', 'auth/ResetPasswordPage'],
]);
const profileRoutes = mapRoutes([
  ['/profile', 'shared/ProfilePage'],
  ['/profile/edit', 'shared/EditProfilePage'],
]);

type RouterFlags = {
  isDevelopment: boolean;
  fakeSmsPageEnabled: boolean;
};

export function buildRouteObjects({
  isDevelopment,
  fakeSmsPageEnabled,
}: RouterFlags): RouteObject[] {
  const developmentRoutes =
    isDevelopment && fakeSmsPageEnabled && localPhoneVerificationPath
      ? [{ path: localPhoneVerificationPath, element: developmentPage() }]
      : [];

  return [
    {
      element: <MainLayout />,
      children: [
        ...publicRoutes,
        ...developmentRoutes,
        { path: '*', element: page('public/NotFoundPage') },
      ],
    },
    {
      element: <ProtectedRoute />,
      children: [
        {
          element: <AuthenticatedLayout />,
          children: [
            { path: '/onboarding', element: page('shared/OnboardingPage') },
            { element: <ProfileGate />, children: profileRoutes },
          ],
        },
      ],
    },
    {
      element: <GuestRoute />,
      children: [{ element: <AuthLayout />, children: guestRoutes }],
    },
  ];
}

export const router = createBrowserRouter(
  buildRouteObjects({
    isDevelopment: import.meta.env.DEV,
    fakeSmsPageEnabled: import.meta.env.VITE_ENABLE_FAKE_SMS_DEV_PAGE === 'true',
  }),
);
