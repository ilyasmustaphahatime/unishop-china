import { Navigate, Outlet } from 'react-router';
import { useAuthStore } from '../stores/authStore';
type Role = 'BUYER' | 'SELLER' | 'ADMIN';
export default function RoleRoute({ allow }: { allow: Role[] }) { return useAuthStore((s) => allow.some((role) => s.roles.includes(role))) ? <Outlet /> : <Navigate to="/" replace />; }
