import { useParams } from 'react-router';
import Alert from '../../components/common/Alert';
import Avatar from '../../components/common/Avatar';
import Badge from '../../components/common/Badge';
import Card from '../../components/common/Card';
import EmptyState from '../../components/common/EmptyState';
import Spinner from '../../components/common/Spinner';
import { profileErrorMessage } from '../../features/profiles/errors';
import { usePublicProfile } from '../../features/profiles/hooks';

export default function PublicProfilePage() {
  const { publicId } = useParams();
  const profile = usePublicProfile(publicId);
  if (profile.isPending) return <Spinner label="Loading public profile" />;
  if (profile.isError || !profile.data) return <Alert>{profileErrorMessage(profile.error)}</Alert>;
  const data = profile.data;
  return (
    <div className="mx-auto max-w-3xl">
      <Card className="p-6 sm:p-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <Avatar name={data.displayName} size="lg" />
          <div>
            <h1 className="text-3xl font-black tracking-tight">{data.displayName}</h1>
            <p className="mt-1 font-medium text-slate-500">{data.city}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge positive={data.emailVerified}>Email {data.emailVerified ? 'verified' : 'not verified'}</Badge>
              <Badge positive={data.phoneVerified}>Phone {data.phoneVerified ? 'verified' : 'not verified'}</Badge>
            </div>
          </div>
        </div>
        <div className="mt-7 border-t border-slate-100 pt-6">
          {data.bio ? <p className="whitespace-pre-wrap break-words leading-7 text-slate-700">{data.bio}</p> : <EmptyState title="No public bio" description="This member has not added an introduction yet." />}
          <p className="mt-6 text-sm text-slate-500">Member since {new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' }).format(new Date(data.memberSince))}</p>
        </div>
      </Card>
    </div>
  );
}
