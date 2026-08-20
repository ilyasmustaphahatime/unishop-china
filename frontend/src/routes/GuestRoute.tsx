import { Navigate, Outlet } from 'react-router';
import AuthLoading from '../components/auth/AuthLoading';
import { useAuthStore } from '../stores/authStore';
import { dashboardForRoles } from './routePaths';

export default function GuestRoute() {
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);
  if (status === 'bootstrapping') return <AuthLoading />;
  return status === 'authenticated' ? (
    <Navigate to={dashboardForRoles(user?.roles ?? [])} replace />
  ) : (
    <Outlet />
  );
}
