import { Link, Outlet } from 'react-router';
import AuthActions from '../auth/AuthActions';

export default function MainLayout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white">
        <nav className="mx-auto flex max-w-6xl items-center gap-5 p-4" aria-label="Main navigation">
          <Link to="/" className="font-bold text-red-600">
            UniShop China
          </Link>
          <Link to="/marketplace">Marketplace</Link>
          <Link to="/safety">Safety</Link>
          <AuthActions />
        </nav>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Outlet />
      </main>
    </div>
  );
}
