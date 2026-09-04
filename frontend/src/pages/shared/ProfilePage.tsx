import { Link, useLocation } from 'react-router';
import Alert from '../../components/common/Alert';
import Avatar from '../../components/common/Avatar';
import Badge from '../../components/common/Badge';
import Card from '../../components/common/Card';
import EmptyState from '../../components/common/EmptyState';
import Spinner from '../../components/common/Spinner';
import { useMyProfile } from '../../features/profiles/hooks';

export default function ProfilePage() {
  const profile = useMyProfile();
  const location = useLocation();
  if (profile.isPending) return <Spinner label="Loading your profile" />;
  if (!profile.data) return <Alert>Your profile could not be loaded.</Alert>;
  const data = profile.data;
  const updated = Boolean((location.state as { profileUpdated?: unknown } | null)?.profileUpdated);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {updated && <Alert tone="success">Your profile was updated.</Alert>}
      <Card className="overflow-hidden">
        <div className="h-28 bg-gradient-to-r from-red-600 via-rose-500 to-amber-400" aria-hidden="true" />
        <div className="px-6 pb-7 sm:px-8">
          <div className="-mt-12 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <Avatar name={data.displayName} size="lg" />
            <Link className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-800 hover:border-red-300 hover:text-red-700" to="/profile/edit">Edit profile</Link>
          </div>
          <h1 className="mt-5 text-3xl font-black tracking-tight">{data.displayName}</h1>
          <p className="mt-1 font-medium text-slate-500">{data.city}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge positive={data.emailVerified}>Email {data.emailVerified ? 'verified' : 'not verified'}</Badge>
            <Badge positive={data.phoneVerified}>Phone {data.phoneVerified ? 'verified' : 'not verified'}</Badge>
          </div>
        </div>
      </Card>
      <Card className="p-6 sm:p-8">
        <h2 className="text-lg font-black">About</h2>
        {data.bio ? <p className="mt-3 whitespace-pre-wrap break-words leading-7 text-slate-700">{data.bio}</p> : <div className="mt-4"><EmptyState title="No bio yet" description="Add a short introduction so the community can get to know you." /></div>}
        <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">Member since {new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' }).format(new Date(data.memberSince))}</p>
      </Card>
    </div>
  );
}
