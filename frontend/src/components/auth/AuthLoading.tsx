export default function AuthLoading() {
  return (
    <div className="flex min-h-48 items-center justify-center" role="status" aria-live="polite">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-red-600" />
      <span className="ml-3 text-sm font-medium text-slate-600">Checking your session…</span>
    </div>
  );
}
