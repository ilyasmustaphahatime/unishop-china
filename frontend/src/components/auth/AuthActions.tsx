import { Link, useNavigate } from 'react-router';
import { useLogoutAllMutation, useLogoutMutation } from '../../features/auth/hooks';
import { useAuthStore } from '../../stores/authStore';

export default function AuthActions() {
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
      <Link className="ml-auto font-semibold text-red-700 hover:underline" to="/login">
        Sign in
      </Link>
    ) : null;
  }

  return (
    <div className="ml-auto flex items-center gap-3">
      <button
        className="text-sm font-semibold text-slate-700 hover:text-red-700 disabled:opacity-50"
        disabled={pending}
        onClick={endCurrentSession}
        type="button"
      >
        Sign out
      </button>
      <button
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:border-red-300 hover:text-red-700 disabled:opacity-50"
        disabled={pending}
        onClick={endAllSessions}
        type="button"
      >
        Sign out everywhere
      </button>
    </div>
  );
}
