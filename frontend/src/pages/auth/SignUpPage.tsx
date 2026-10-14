import { useAppTranslation } from '../../i18n/useAppTranslation';
export default function SignUpPage() {
  const { t } = useAppTranslation(); return <h1 className="text-3xl font-bold">{t('auth:signUpTitle')}</h1>; }
