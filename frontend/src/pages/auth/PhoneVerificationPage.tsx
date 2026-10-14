import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function PhoneVerificationPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('auth:phoneTitle')}</h1>; }
