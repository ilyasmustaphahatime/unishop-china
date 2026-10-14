import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function ForgotPasswordPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('auth:forgotTitle')}</h1>; }
