import { zodResolver } from '@hookform/resolvers/zod';
import axios from 'axios';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useLocation, useNavigate } from 'react-router';
import { useLoginMutation } from '../../features/auth/hooks';
import { loginSchema, type LoginFormValues } from '../../features/auth/schemas';
import type { UserRole } from '../../features/auth/types';
import { useAuthStore } from '../../stores/authStore';

function dashboardFor(roles: UserRole[]) {
  if (roles.includes('ADMIN')) return '/admin';
  if (roles.includes('SELLER')) return '/seller/dashboard';
  return '/buyer/dashboard';
}

function errorMessage(error: unknown) {
  if (axios.isAxiosError<{ detail?: string }>(error)) {
    if (!error.response) return 'Unable to reach UniShop China. Check your connection and try again.';
    if (error.response.status === 401) return 'The email, phone number, or password is incorrect.';
    if (error.response.status === 403) return error.response.data.detail ?? 'This account cannot sign in right now.';
    return error.response.data.detail ?? 'Sign in failed. Please try again.';
  }
  return 'Something unexpected happened. Please try again.';
}

export default function LoginForm() {
  const [showPassword, setShowPassword] = useState(false);
  const mutation = useLoginMutation();
  const completeLogin = useAuthStore((state) => state.completeLogin);
  const navigate = useNavigate();
  const location = useLocation();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: '', password: '' },
  });

  async function onSubmit(values: LoginFormValues) {
    try {
      const session = await mutation.mutateAsync(values);
      completeLogin(session);
      const requestedPath = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(requestedPath || dashboardFor(session.user.roles), { replace: true });
    } catch (error) {
      setError('root.server', { message: errorMessage(error) });
    }
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
      {errors.root?.server && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          {errors.root.server.message}
        </div>
      )}

      <div>
        <label className="mb-2 block text-sm font-semibold text-slate-800" htmlFor="identifier">
          Email address or phone number
        </label>
        <input
          id="identifier"
          autoComplete="username"
          autoFocus
          aria-invalid={Boolean(errors.identifier)}
          aria-describedby={errors.identifier ? 'identifier-error' : undefined}
          className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-red-500 focus:ring-4 focus:ring-red-100"
          placeholder="you@example.com or +86…"
          {...register('identifier')}
        />
        {errors.identifier && <p className="mt-2 text-sm text-red-700" id="identifier-error">{errors.identifier.message}</p>}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-4">
          <label className="text-sm font-semibold text-slate-800" htmlFor="password">Password</label>
          <Link className="text-sm font-semibold text-red-700 hover:text-red-800 hover:underline" to="/forgot-password">
            Forgot password?
          </Link>
        </div>
        <div className="relative">
          <input
            id="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 pr-20 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-red-500 focus:ring-4 focus:ring-red-100"
            placeholder="Enter your password"
            {...register('password')}
          />
          <button
            className="absolute inset-y-0 right-0 px-4 text-sm font-semibold text-slate-600 hover:text-slate-950"
            type="button"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            onClick={() => setShowPassword((visible) => !visible)}
          >
            {showPassword ? 'Hide' : 'Show'}
          </button>
        </div>
        {errors.password && <p className="mt-2 text-sm text-red-700" id="password-error">{errors.password.message}</p>}
      </div>

      <button
        className="flex w-full items-center justify-center rounded-xl bg-red-600 px-4 py-3 font-bold text-white shadow-sm transition hover:bg-red-700 focus:outline-none focus:ring-4 focus:ring-red-200 disabled:cursor-not-allowed disabled:opacity-65"
        disabled={mutation.isPending}
        type="submit"
      >
        {mutation.isPending ? 'Signing in…' : 'Sign in'}
      </button>

      <p className="text-center text-sm text-slate-600">
        New to UniShop China?{' '}
        <Link className="font-bold text-red-700 hover:text-red-800 hover:underline" to="/sign-up">Create an account</Link>
      </p>
    </form>
  );
}
