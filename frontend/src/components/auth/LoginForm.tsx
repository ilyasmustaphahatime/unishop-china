import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { zodResolver } from '@hookform/resolvers/zod';
import axios from 'axios';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useLocation, useNavigate } from 'react-router';
import { useLoginMutation } from '../../features/auth/hooks';
import { loginSchema, type LoginFormValues } from '../../features/auth/schemas';
import { dashboardForRoles, safeInternalPath } from '../../routes/routePaths';
import { useAuthStore } from '../../stores/authStore';

function errorMessage(error: unknown) {
  if (axios.isAxiosError<{ detail?: string }>(error)) {
    if (!error.response) return 'Unable to reach UniShop China. Check your connection and try again.';
    if (error.response.status === 401 || error.response.status === 403) {
      return 'The email, phone number, or password is incorrect, or this account cannot sign in.';
    }
    if (error.response.status === 422) return 'Check your email or phone number and password, then try again.';
    if (error.response.status === 429) return 'Too many sign-in attempts. Wait a moment and try again.';
    return 'Sign in failed. Please try again.';
  }
  return 'Something unexpected happened. Please try again.';
}

export default function LoginForm() {
  const { t } = useAppTranslation();
  const [showPassword, setShowPassword] = useState(false);
  const mutation = useLoginMutation();
  const setAuthenticated = useAuthStore((state) => state.setAuthenticated);
  const navigate = useNavigate();
  const location = useLocation();
  const logoutUnconfirmed = Boolean(
    (location.state as { logoutUnconfirmed?: unknown } | null)?.logoutUnconfirmed,
  );
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: '', password: '' },
  });

  async function onSubmit(values: LoginFormValues) {
    try {
      const session = await mutation.mutateAsync(values);
      setAuthenticated(session.accessToken, session.user);
      reset({ identifier: values.identifier, password: '' });
      const requestedLocation = (location.state as { from?: unknown } | null)?.from;
      const destination = safeInternalPath(
        requestedLocation,
        dashboardForRoles(session.user.roles),
      );
      navigate(destination, { replace: true });
    } catch (error) {
      setError('root.server', { message: errorMessage(error) });
    }
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
      {logoutUnconfirmed && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
          {t('auth:logoutUnconfirmed')}</div>
      )}
      {errors.root?.server && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          {localizeMessage(errors.root.server.message)}
        </div>
      )}

      <div>
        <label className="mb-2 block text-sm font-semibold text-slate-800" htmlFor="identifier">
          {t('auth:identifier')}</label>
        <input
          id="identifier"
          dir="ltr"
          autoComplete="username"
          autoFocus
          aria-invalid={Boolean(errors.identifier)}
          aria-describedby={errors.identifier ? 'identifier-error' : undefined}
          className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-red-500 focus:ring-4 focus:ring-red-100"
          placeholder={t('auth:identifierPlaceholder')}
          {...register('identifier')}
        />
        {errors.identifier && <p className="mt-2 text-sm text-red-700" id="identifier-error">{localizeMessage(errors.identifier.message, 'validation:fieldInvalid')}</p>}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-4">
          <label className="text-sm font-semibold text-slate-800" htmlFor="password">{t('auth:password')}</label>
          <Link className="text-sm font-semibold text-red-700 hover:text-red-800 hover:underline" to="/forgot-password">
            {t('auth:forgotPassword')}</Link>
        </div>
        <div className="relative">
          <input
            id="password"
            dir="ltr"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className="w-full rounded-xl border border-slate-300 bg-white password-input px-4 py-3 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-red-500 focus:ring-4 focus:ring-red-100"
            placeholder={t('auth:passwordPlaceholder')}
            {...register('password')}
          />
          <button
            className="absolute inset-y-0 end-0 px-4 text-sm font-semibold text-slate-600 hover:text-slate-950"
            type="button"
            aria-label={showPassword ? t('auth:hidePassword') : t('auth:showPassword')}
            onClick={() => setShowPassword((visible) => !visible)}
          >
            {showPassword ? t('auth:hide') : t('auth:show')}
          </button>
        </div>
        {errors.password && <p className="mt-2 text-sm text-red-700" id="password-error">{localizeMessage(errors.password.message, 'validation:fieldInvalid')}</p>}
      </div>

      <button
        className="flex w-full items-center justify-center rounded-xl bg-red-600 px-4 py-3 font-bold text-white shadow-sm transition hover:bg-red-700 focus:outline-none focus:ring-4 focus:ring-red-200 disabled:cursor-not-allowed disabled:opacity-65"
        disabled={mutation.isPending}
        type="submit"
      >
        {mutation.isPending ? t('auth:signingIn') : t('common:signIn')}
      </button>

      <p className="text-center text-sm text-slate-600">
        {t('auth:newMember')}{' '}
        <Link className="font-bold text-red-700 hover:text-red-800 hover:underline" to="/sign-up">{t('auth:createAccount')}</Link>
      </p>
    </form>
  );
}
