import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link, useNavigate } from 'react-router';
import { useLogoutAllMutation, useLogoutMutation } from '../../features/auth/hooks';
import { useAuthStore } from '../../stores/authStore';

export default function AuthActions() {
  const { t } = useAppTranslation();
  const status = useAuthStore((state) => state.status);
  const logout = useLogoutMutation();
  const logoutAll = useLogoutAllMutation();
  const navigate = useNavigate();
  const pending = logout.isPending || logoutAll.isPending;

  async function endCurrentSession() {
    const confirmed = await logout.mutateAsync().then(
      () => true,
      () => false,
    );
    navigate('/login', {
      replace: true,
      state: confirmed ? undefined : { logoutUnconfirmed: true },
    });
  }

  async function endAllSessions() {
    const confirmed = await logoutAll.mutateAsync().then(
      () => true,
      () => false,
    );
    navigate('/login', {
      replace: true,
      state: confirmed ? undefined : { logoutUnconfirmed: true },
    });
  }

  if (status !== 'authenticated') {
    return status === 'unauthenticated' ? (
      <Link className="ms-auto font-semibold text-red-700 hover:underline" to="/login">
        {t('common:signIn')}</Link>
    ) : null;
  }

  return (
    <div className="ms-auto flex items-center gap-3">
      <button
        className="text-sm font-semibold text-slate-700 hover:text-red-700 disabled:opacity-50"
        disabled={pending}
        onClick={endCurrentSession}
        type="button"
      >
        {t('common:signOut')}</button>
      <button
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:border-red-300 hover:text-red-700 disabled:opacity-50"
        disabled={pending}
        onClick={endAllSessions}
        type="button"
      >
        {t('common:signOutAll')}</button>
    </div>
  );
}
