import { verificationStatusKeys } from '../../i18n/labels';
import { formatDate } from '../../i18n/formatters';
import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { useAuthStore } from '../../stores/authStore';
import { useVerification, useVerificationMutation } from '../../features/sellerVerification/hooks';
import { evidenceTypes, validateEvidenceFile } from '../../features/sellerVerification/schemas';
import type { EvidenceType } from '../../features/sellerVerification/types';

const labels = {
  SELFIE: 'verification:selfie', WECHAT_PROOF: 'verification:wechatProof', HANDWRITTEN_CODE: 'verification:handwrittenCode',
} as const;
const uploadLabels = {
  SELFIE: 'verification:uploadSelfie', WECHAT_PROOF: 'verification:uploadWechat', HANDWRITTEN_CODE: 'verification:uploadHandwritten',
} as const;
const button = 'rounded-lg bg-red-700 px-4 py-2 font-semibold text-white disabled:opacity-50';

function VerificationForm() {
  const { t } = useAppTranslation();
  const user = useAuthStore((s) => s.user);
  const query = useVerification();
  const mutation = useVerificationMutation();
  const [files, setFiles] = useState<Partial<Record<EvidenceType, File>>>({});
  const [message, setMessage] = useState('');
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const eligible = Boolean(user?.emailVerified && user?.phoneVerified);
  if (query.isPending) return <p role="status">{t('verification:loading')}</p>;
  if (query.isError) return <div role="alert">{t('verification:loadFailed')}<button type="button" onClick={() => void query.refetch()}>{t('common:retry')}</button></div>;
  const data = query.data;
  const pending = data?.status === 'PENDING';
  const expired = Boolean(data && Date.parse(data.challenge_expires_at) <= now);
  const complete = evidenceTypes.every((kind) => data?.evidence.some((e) => e.evidence_type === kind));

  async function change(action: 'start' | 'submit' | 'renew_challenge') {
    setMessage('');
    try { await mutation.mutateAsync({ action }); setFiles({}); }
    catch { setMessage('Unable to continue. Check your verification status and try again.'); }
  }
  async function upload(event: FormEvent, kind: EvidenceType) {
    event.preventDefault();
    const file = files[kind];
    if (!file) { setMessage('Choose an image first.'); return; }
    const error = validateEvidenceFile(file);
    if (error) { setMessage(error); return; }
    setMessage('');
    try {
      await mutation.mutateAsync({ action: 'upload', kind, file,
        challenge: kind === 'HANDWRITTEN_CODE' ? data?.handwritten_challenge : undefined });
      setFiles((previous) => ({ ...previous, [kind]: undefined }));
      setMessage('Evidence uploaded privately.');
    } catch { setMessage('Upload failed. Use a valid JPEG or PNG image and try again.'); }
  }
  return <section className="mx-auto max-w-2xl space-y-6 rounded-xl bg-white p-6 shadow-sm">
    <Link to="/profile" className="text-red-700 underline">{t('verification:backProfile')}</Link>
    <h1 className="text-2xl font-bold">{t('verification:sellerTitle')}</h1>
    <p>{t('verification:privacyCopy')}</p>
    {!eligible && <p role="alert">{t('verification:eligibility')}</p>}
    {message && <p role="status">{localizeMessage(message)}</p>}
    {data && <p>{t('verification:status', { status: t(verificationStatusKeys[data.status]) })}</p>}
    {data?.status === 'REJECTED' && <p>{t('verification:feedback')}{' '}<bdi>{data.rejection_reason}</bdi></p>}
    {(!data || data.status === 'REJECTED') && <button className={button} disabled={!eligible || mutation.isPending}
      onClick={() => void change('start')}>{t('verification:start')}</button>}
    {pending && <div key={data.handwritten_challenge}>
      <p>{t('verification:challengeInstruction')}<strong dir="ltr" className="ms-2 font-mono">{data.handwritten_challenge}</strong>.</p>
      <p>{t('verification:challengeExpiry', { time: formatDate(data.challenge_expires_at, { timeStyle: 'medium' }) })}</p>
      {expired && <p role="alert">{t('verification:expiredChallenge')}</p>}
      <button className={button} disabled={!eligible || mutation.isPending}
        onClick={() => void change('renew_challenge')}>{t('verification:renew')}</button>
      <p>{t('verification:renewCopy')}</p>
      <p>{t('verification:evidenceConstraints')}</p>
      {evidenceTypes.map((kind) => <form key={kind} onSubmit={(event) => void upload(event, kind)}
        className="space-y-2 border-t pt-4">
        <label className="block font-semibold" htmlFor={kind}>{t(labels[kind])}</label>
        {data.evidence.some((e) => e.evidence_type === kind) && <p>{t('verification:uploaded')}</p>}
        <input id={kind} type="file" accept="image/jpeg,image/png" disabled={!eligible || mutation.isPending}
          onChange={(event) => setFiles((previous) => ({ ...previous, [kind]: event.target.files?.[0] }))} />
        <button className={button} disabled={!eligible || mutation.isPending || !files[kind]}>
          {t(uploadLabels[kind])}</button>
      </form>)}
      <button className={button} disabled={!eligible || !complete || expired || mutation.isPending}
        onClick={() => void change('submit')}>{t('verification:submit')}</button>
    </div>}
    {data?.status === 'UNDER_REVIEW' && <p>{t('verification:reviewCopy')}</p>}
    {data?.status === 'VERIFIED' && <p>{t('verification:approvedCopy')}</p>}
  </section>;
}

export default function SellerVerificationPage() {
  const version = useAuthStore((s) => s.sessionVersion);
  return <VerificationForm key={version} />;
}
