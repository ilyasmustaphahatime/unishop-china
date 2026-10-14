import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function NotFoundPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('common:notFoundTitle')}</h1>; }
