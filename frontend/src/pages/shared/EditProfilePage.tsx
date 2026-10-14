import { useAppTranslation } from '../../i18n/useAppTranslation';
import Card from '../../components/common/Card';
import ProfileForm from '../../components/profiles/ProfileForm';
import Alert from '../../components/common/Alert';
import Spinner from '../../components/common/Spinner';
import { useMyProfile } from '../../features/profiles/hooks';

export default function EditProfilePage() {
  const { t } = useAppTranslation();
  const profile = useMyProfile();
  if (profile.isPending) return <Spinner label={t('profile:loadingOwn')} />;
  if (!profile.data) return <Alert>{t('profile:loadFailed')}</Alert>;
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <p className="text-sm font-bold uppercase tracking-wider text-red-600">{t('profile:accountProfile')}</p>
        <h1 className="mt-2 text-3xl font-black tracking-tight">{t('common:editProfile')}</h1>
        <p className="mt-2 text-slate-600">{t('profile:identityCopy')}</p>
      </div>
      <Card className="p-6 sm:p-8"><ProfileForm profile={profile.data} /></Card>
    </div>
  );
}
