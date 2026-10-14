import { useAppTranslation } from '../../i18n/useAppTranslation';
import LoginForm from '../../components/auth/LoginForm';

export default function LoginPage() {
  const { t } = useAppTranslation();
  return (
    <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-900/5 sm:p-8">
      <div className="mb-7">
        <p className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-red-600">{t('auth:welcomeBack')}</p>
        <h1 className="text-3xl font-black tracking-tight text-slate-950">{t('auth:loginTitle')}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          {t('auth:accessCopy')}</p>
      </div>
      <LoginForm />
      <p className="mt-6 border-t border-slate-200 pt-5 text-center text-xs leading-5 text-slate-500">
        {t('auth:paymentNotice')}</p>
    </section>
  );
}
