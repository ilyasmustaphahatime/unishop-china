import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function Spinner({ label }: { label?: string }) {
  const { t } = useAppTranslation();
  return (
    <div className="flex min-h-40 items-center justify-center gap-3 text-sm font-semibold text-slate-600" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-red-600" aria-hidden="true" />
      <span>{label ?? t('common:loading')}</span>
    </div>
  );
}
