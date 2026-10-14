import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function TermsPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('common:termsTitle')}</h1>; }
