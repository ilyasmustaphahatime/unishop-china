import { formatDate } from '../../i18n/formatters';
import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useParams } from 'react-router';
import Alert from '../../components/common/Alert';
import Avatar from '../../components/common/Avatar';
import Badge from '../../components/common/Badge';
import Card from '../../components/common/Card';
import EmptyState from '../../components/common/EmptyState';
import Spinner from '../../components/common/Spinner';
import { profileErrorMessage } from '../../features/profiles/errors';
import { usePublicProfile } from '../../features/profiles/hooks';
import { normalizePublicHandle } from '../../features/profiles/handles';

export default function PublicProfilePage() {
  const { t } = useAppTranslation();
  const { handle } = useParams();
  const profile = usePublicProfile(handle);
  if (!handle || !normalizePublicHandle(handle)) return <Alert>{t('profile:unavailable')}</Alert>;
  if (profile.isPending) return <Spinner label={t('profile:loadingPublic')} />;
  if (profile.isError || !profile.data) return <Alert>{localizeMessage(profileErrorMessage(profile.error))}</Alert>;
  const data = profile.data;
  return (
    <div className="mx-auto max-w-3xl">
      <Card className="p-6 sm:p-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <Avatar name={data.displayName} size="lg" />
          <div>
            <h1 dir="auto" className="text-3xl font-black tracking-tight">{data.displayName}</h1>
            <p dir="auto" className="mt-1 font-medium text-slate-500">{data.city}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {data.sellerVerified && <Badge positive>{t('profile:sellerVerified')}</Badge>}
              <Badge positive={data.emailVerified}>{t(data.emailVerified ? 'profile:emailVerified' : 'profile:emailNotVerified')}</Badge>
              <Badge positive={data.phoneVerified}>{t(data.phoneVerified ? 'profile:phoneVerified' : 'profile:phoneNotVerified')}</Badge>
            </div>
          </div>
        </div>
        <div className="mt-7 border-t border-slate-100 pt-6">
          {data.bio ? <p dir="auto" className="whitespace-pre-wrap break-words leading-7 text-slate-700">{data.bio}</p> : <EmptyState title={t('profile:noPublicBio')} description={t('profile:memberNoIntro')} />}
          <p className="mt-6 text-sm text-slate-500">{t('profile:memberSince', { date: formatDate(data.memberSince, { month: 'long', year: 'numeric' }) })}</p>
        </div>
      </Card>
    </div>
  );
}
