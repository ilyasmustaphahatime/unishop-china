import { Navigate, Outlet } from 'react-router';
import { useAuthStore } from '../stores/authStore';
export default function GuestRoute() { return useAuthStore((s) => s.isAuthenticated) ? <Navigate to="/buyer/dashboard" replace /> : <Outlet />; }
