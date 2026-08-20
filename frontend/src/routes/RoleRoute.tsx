import { Navigate, Outlet } from 'react-router';
import type { UserRole } from '../features/auth/types';
import { useAuthStore } from '../stores/authStore';

export default function RoleRoute({ allow }: { allow: UserRole[] }) {
  const user = useAuthStore((state) => state.user);
  // This improves navigation UX only; the backend remains the authorization boundary.
  return allow.some((role) => user?.roles.includes(role)) ? <Outlet /> : <Navigate to="/" replace />;
}
