import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuthStore } from '../stores/authStore';
export default function ProtectedRoute() {
  const location = useLocation();
  return useAuthStore((s) => s.isAuthenticated) ? <Outlet /> : <Navigate to="/login" replace state={{ from: location }} />;
}
