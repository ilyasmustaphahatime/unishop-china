import Card from '../../components/common/Card';
import ProfileForm from '../../components/profiles/ProfileForm';
import Alert from '../../components/common/Alert';
import Spinner from '../../components/common/Spinner';
import { useMyProfile } from '../../features/profiles/hooks';

export default function EditProfilePage() {
  const profile = useMyProfile();
  if (profile.isPending) return <Spinner label="Loading your profile" />;
  if (!profile.data) return <Alert>Your profile could not be loaded.</Alert>;
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <p className="text-sm font-bold uppercase tracking-wider text-red-600">Account profile</p>
        <h1 className="mt-2 text-3xl font-black tracking-tight">Edit profile</h1>
        <p className="mt-2 text-slate-600">Keep your public marketplace identity clear and current.</p>
      </div>
      <Card className="p-6 sm:p-8"><ProfileForm profile={profile.data} /></Card>
    </div>
  );
}
