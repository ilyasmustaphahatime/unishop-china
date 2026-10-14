import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function HomePage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('common:homeTitle')}</h1>; }
