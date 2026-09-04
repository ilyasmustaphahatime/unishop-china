import { Link, NavLink, Outlet } from 'react-router';
import AuthActions from '../auth/AuthActions';
import Avatar from '../common/Avatar';
import { useAuthStore } from '../../stores/authStore';

export default function AuthenticatedLayout() {
  const user = useAuthStore((state) => state.user);
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-semibold transition ${
      isActive ? 'bg-red-50 text-red-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
    }`;
  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3 sm:px-6" aria-label="Account navigation">
          <Link className="mr-2 flex items-center gap-2 font-black tracking-tight text-red-600" to="/profile">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-red-600 text-sm text-white" aria-hidden="true">中</span>
            UniShop China
          </Link>
          <div className="order-3 flex w-full gap-1 border-t border-slate-100 pt-2 sm:order-none sm:w-auto sm:border-0 sm:pt-0">
            <NavLink className={linkClass} to="/profile" end>My profile</NavLink>
            <NavLink className={linkClass} to="/profile/edit">Edit profile</NavLink>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Avatar name={user?.email ?? user?.phoneNumber ?? null} size="sm" />
            <AuthActions />
          </div>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}
