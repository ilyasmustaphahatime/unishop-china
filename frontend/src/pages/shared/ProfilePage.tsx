import { formatDate } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link, useLocation } from 'react-router';
import Alert from '../../components/common/Alert';
import Avatar from '../../components/common/Avatar';
import Badge from '../../components/common/Badge';
import Card from '../../components/common/Card';
import EmptyState from '../../components/common/EmptyState';
import Spinner from '../../components/common/Spinner';
import { useMyProfile } from '../../features/profiles/hooks';
import { publicProfilePath } from '../../features/profiles/handles';

export default function ProfilePage() {
  const { t } = useAppTranslation();
  const profile = useMyProfile();
  const location = useLocation();
  if (profile.isPending) return <Spinner label={t('profile:loadingOwn')} />;
  if (!profile.data) return <Alert>{t('profile:loadFailed')}</Alert>;
  const data = profile.data;
  const updated = Boolean((location.state as { profileUpdated?: unknown } | null)?.profileUpdated);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {updated && <Alert tone="success">{t('profile:updated')}</Alert>}
      <Card className="overflow-hidden">
        <div className="h-28 bg-gradient-to-r from-red-600 via-rose-500 to-amber-400" aria-hidden="true" />
        <div className="px-6 pb-7 sm:px-8">
          <div className="-mt-12 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <Avatar name={data.displayName} size="lg" />
            <Link className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-800 hover:border-red-300 hover:text-red-700" to="/profile/edit">{t('common:editProfile')}</Link>
          </div>
          <h1 dir="auto" className="mt-5 text-3xl font-black tracking-tight">{data.displayName}</h1>
          <Link className="block text-red-700 hover:underline" to="/seller/verification">{t('verification:sellerTitle')}</Link>
          <Link className="text-red-700 hover:underline" to={publicProfilePath(data.publicHandle)}>{t('profile:viewPublic')}</Link>
          <p dir="auto" className="mt-1 font-medium text-slate-500">{data.city}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge positive={data.emailVerified}>{t(data.emailVerified ? 'profile:emailVerified' : 'profile:emailNotVerified')}</Badge>
            <Badge positive={data.phoneVerified}>{t(data.phoneVerified ? 'profile:phoneVerified' : 'profile:phoneNotVerified')}</Badge>
          </div>
        </div>
      </Card>
      <Card className="p-6 sm:p-8">
        <h2 className="text-lg font-black">{t('profile:about')}</h2>
        {data.bio ? <p dir="auto" className="mt-3 whitespace-pre-wrap break-words leading-7 text-slate-700">{data.bio}</p> : <div className="mt-4"><EmptyState title={t('profile:noBio')} description={t('profile:addBio')} /></div>}
        <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">{t('profile:memberSince', { date: formatDate(data.memberSince, { month: 'long', year: 'numeric' }) })}</p>
      </Card>
    </div>
  );
}
