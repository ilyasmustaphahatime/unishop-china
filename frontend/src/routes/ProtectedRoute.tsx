import { Navigate, Outlet, useLocation } from 'react-router';
import AuthLoading from '../components/auth/AuthLoading';
import { useAuthStore } from '../stores/authStore';

export default function ProtectedRoute() {
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  if (status === 'bootstrapping') return <AuthLoading />;
  return status === 'authenticated' ? (
    <Outlet />
  ) : (
    <Navigate to="/login" replace state={{ from: location }} />
  );
}
