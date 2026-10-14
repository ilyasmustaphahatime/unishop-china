import { default as LanguageSwitcher } from './LanguageSwitcher';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link, Outlet } from 'react-router';
import AuthActions from '../auth/AuthActions';

export default function MainLayout() {
  const { t } = useAppTranslation();
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 p-4" aria-label={t('common:mainNavigation')}>
          <Link to="/" className="font-bold text-red-600">
            UniShop China
          </Link>
          <Link to="/safety">{t('common:safety')}</Link>
          <LanguageSwitcher />
          <AuthActions />
        </nav>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Outlet />
      </main>
    </div>
  );
}
