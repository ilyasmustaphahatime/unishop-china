import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter, type RouteObject } from 'react-router-dom';
import AuthLayout from '../components/layout/AuthLayout';
import MainLayout from '../components/layout/MainLayout';
import GuestRoute from '../routes/GuestRoute';
import ProtectedRoute from '../routes/ProtectedRoute';
import RoleRoute from '../routes/RoleRoute';

const pages = import.meta.glob('../pages/**/*.tsx');

function page(path: string) {
  const Page = lazy(pages[`../pages/${path}.tsx`] as () => Promise<{ default: ComponentType }>);
  return <Suspense fallback={<p className="p-6 text-slate-600">Loading…</p>}><Page /></Suspense>;
}

function mapRoutes(routes: Array<[string, string]>): RouteObject[] {
  return routes.map(([path, component]) => ({ path, element: page(component) }));
}

const publicRoutes = mapRoutes([
  ['/', 'public/HomePage'], ['/marketplace', 'public/MarketplacePage'], ['/products/:productId', 'public/ProductDetailsPage'],
  ['/sellers/:sellerId', 'public/SellerPublicProfilePage'], ['/safety', 'public/SafetyPage'], ['/terms', 'public/TermsPage'], ['/privacy', 'public/PrivacyPage'],
]);
const guestRoutes = mapRoutes([
  ['/login', 'auth/LoginPage'], ['/sign-up', 'auth/SignUpPage'], ['/verify-phone', 'auth/PhoneVerificationPage'],
  ['/forgot-password', 'auth/ForgotPasswordPage'], ['/reset-password', 'auth/ResetPasswordPage'],
]);
const buyerRoutes = mapRoutes([
  ['/buyer/dashboard', 'buyer/BuyerDashboardPage'], ['/buyer/profile', 'buyer/BuyerProfilePage'], ['/buyer/favorites', 'buyer/FavoritesPage'],
  ['/buyer/deals', 'buyer/BuyerDealsPage'], ['/buyer/reviews', 'buyer/BuyerReviewsPage'], ['/buyer/recently-viewed', 'buyer/RecentlyViewedPage'],
]);
const sellerRoutes = mapRoutes([
  ['/seller/dashboard', 'seller/SellerDashboardPage'], ['/seller/verification', 'seller/SellerVerificationPage'], ['/seller/products', 'seller/SellerProductsPage'],
  ['/seller/products/new', 'seller/AddProductPage'], ['/seller/products/:productId/edit', 'seller/EditProductPage'], ['/seller/deals', 'seller/SellerDealsPage'],
  ['/seller/reviews', 'seller/SellerReviewsPage'], ['/seller/profile', 'seller/SellerProfilePage'],
]);
const sharedRoutes = mapRoutes([
  ['/messages', 'shared/MessagesPage'], ['/notifications', 'shared/NotificationsPage'], ['/settings', 'shared/SettingsPage'], ['/reports', 'shared/ReportsPage'],
]);
const adminRoutes = mapRoutes([
  ['/admin', 'admin/AdminDashboardPage'], ['/admin/users', 'admin/AdminUsersPage'], ['/admin/seller-verifications', 'admin/AdminSellerVerificationsPage'],
  ['/admin/products', 'admin/AdminProductsPage'], ['/admin/product-proofs', 'admin/AdminProductProofsPage'], ['/admin/reports', 'admin/AdminReportsPage'],
  ['/admin/reviews', 'admin/AdminReviewsPage'], ['/admin/categories', 'admin/AdminCategoriesPage'], ['/admin/cities', 'admin/AdminCitiesPage'],
]);

export const router = createBrowserRouter([
  {
    element: <MainLayout />,
    children: [
      ...publicRoutes,
      {
        element: <ProtectedRoute />,
        children: [
          ...sharedRoutes,
          { element: <RoleRoute allow={['BUYER', 'ADMIN']} />, children: buyerRoutes },
          { element: <RoleRoute allow={['SELLER', 'ADMIN']} />, children: sellerRoutes },
          { element: <RoleRoute allow={['ADMIN']} />, children: adminRoutes },
        ],
      },
      { path: '*', element: page('public/NotFoundPage') },
    ],
  },
  {
    element: <GuestRoute />,
    children: [{ element: <AuthLayout />, children: guestRoutes }],
  },
]);
