import { Navigate, Outlet } from 'react-router';
import Alert from '../common/Alert';
import Button from '../common/Button';
import Spinner from '../common/Spinner';
import { profileErrorMessage } from '../../features/profiles/errors';
import { useMyProfile } from '../../features/profiles/hooks';

export default function ProfileGate() {
  const profile = useMyProfile();
  if (profile.isPending) return <Spinner label="Loading your profile" />;
  if (profile.isError) {
    return (
      <div className="mx-auto max-w-xl py-10">
        <Alert>{profileErrorMessage(profile.error)}</Alert>
        <Button className="mt-4" variant="secondary" onClick={() => void profile.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return profile.data?.onboardingCompleted ? <Outlet /> : <Navigate to="/onboarding" replace />;
}
