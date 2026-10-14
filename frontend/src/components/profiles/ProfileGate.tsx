import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Navigate, Outlet } from 'react-router';
import Alert from '../common/Alert';
import Button from '../common/Button';
import Spinner from '../common/Spinner';
import { profileErrorMessage } from '../../features/profiles/errors';
import { useMyProfile } from '../../features/profiles/hooks';

export default function ProfileGate() {
  const { t } = useAppTranslation();
  const profile = useMyProfile();
  if (profile.isPending) return <Spinner label={t('profile:loadingOwn')} />;
  if (profile.isError) {
    return (
      <div className="mx-auto max-w-xl py-10">
        <Alert>{localizeMessage(profileErrorMessage(profile.error))}</Alert>
        <Button className="mt-4" variant="secondary" onClick={() => void profile.refetch()}>
          {t('common:retry')}</Button>
      </div>
    );
  }
  return profile.data?.onboardingCompleted ? <Outlet /> : <Navigate to="/onboarding" replace />;
}
