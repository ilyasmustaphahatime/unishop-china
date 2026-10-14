import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function ResetPasswordPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('auth:resetTitle')}</h1>; }
