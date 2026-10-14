import { formatNumber } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function ProgressSteps({ current, total }: { current: number; total: number }) {
  const { t } = useAppTranslation();
  return (
    <div aria-label={t('common:step', { current: formatNumber(current), total: formatNumber(total) })}>
      <div className="mb-2 flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-500">
        <span>{t('common:gettingStarted')}</span>
        <span>{t('common:progress', { current: formatNumber(current), total: formatNumber(total) })}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-red-600 transition-all"
          style={{ width: `${Math.round((current / total) * 100)}%` }}
        />
      </div>
    </div>
  );
}
