import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { useAuthStore } from '../../stores/authStore';
import { useVerification, useVerificationMutation } from '../../features/sellerVerification/hooks';
import { evidenceTypes, validateEvidenceFile } from '../../features/sellerVerification/schemas';
import type { EvidenceType } from '../../features/sellerVerification/types';

const labels: Record<EvidenceType, string> = {
  SELFIE: 'Selfie', WECHAT_PROOF: 'WeChat proof', HANDWRITTEN_CODE: 'Handwritten code',
};
const button = 'rounded-lg bg-red-700 px-4 py-2 font-semibold text-white disabled:opacity-50';

function VerificationForm() {
  const user = useAuthStore((s) => s.user);
  const query = useVerification();
  const mutation = useVerificationMutation();
  const [files, setFiles] = useState<Partial<Record<EvidenceType, File>>>({});
  const [message, setMessage] = useState('');
  const eligible = Boolean(user?.emailVerified && user?.phoneVerified);
  if (query.isPending) return <p role="status">Loading seller verification…</p>;
  if (query.isError) return <div role="alert">Verification could not be loaded.
    <button type="button" onClick={() => void query.refetch()}>Try again</button></div>;
  const data = query.data;
  const pending = data?.status === 'PENDING';
  const complete = evidenceTypes.every((kind) => data?.evidence.some((e) => e.evidence_type === kind));

  async function change(action: 'start' | 'submit') {
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
      await mutation.mutateAsync({ action: 'upload', kind, file });
      setFiles((previous) => ({ ...previous, [kind]: undefined }));
      setMessage('Evidence uploaded privately.');
    } catch { setMessage('Upload failed. Use a valid JPEG or PNG image and try again.'); }
  }
  return <section className="mx-auto max-w-2xl space-y-6 rounded-xl bg-white p-6 shadow-sm">
    <Link to="/profile" className="text-red-700 underline">Back to profile</Link>
    <h1 className="text-2xl font-bold">Seller verification</h1>
    <p>Your images are private. Only you and authorized reviewers can access them.
      Do not upload passports, payment details or unrelated personal information.</p>
    {!eligible && <p role="alert">Verify both your email and phone before submitting evidence.</p>}
    {message && <p role="status">{message}</p>}
    {data && <p>Status: <strong>{data.status.replaceAll('_', ' ')}</strong></p>}
    {data?.status === 'REJECTED' && <p>Review feedback: {data.rejection_reason}</p>}
    {(!data || data.status === 'REJECTED') && <button className={button} disabled={!eligible || mutation.isPending}
      onClick={() => void change('start')}>Start verification</button>}
    {pending && <>
      <p>Write this request code on paper and include it in your handwritten-code image:
        <strong className="ml-2 font-mono">{data.handwritten_challenge}</strong>.</p>
      <p>Upload one clear JPEG or PNG for each requirement, at most 5 MiB each.
        You can replace images until you submit.</p>
      {evidenceTypes.map((kind) => <form key={kind} onSubmit={(event) => void upload(event, kind)}
        className="space-y-2 border-t pt-4">
        <label className="block font-semibold" htmlFor={kind}>{labels[kind]}</label>
        {data.evidence.some((e) => e.evidence_type === kind) && <p>Uploaded</p>}
        <input id={kind} type="file" accept="image/jpeg,image/png" disabled={!eligible || mutation.isPending}
          onChange={(event) => setFiles((previous) => ({ ...previous, [kind]: event.target.files?.[0] }))} />
        <button className={button} disabled={!eligible || mutation.isPending || !files[kind]}>
          Upload {labels[kind].toLowerCase()}</button>
      </form>)}
      <button className={button} disabled={!eligible || !complete || mutation.isPending}
        onClick={() => void change('submit')}>Submit for review</button>
    </>}
    {data?.status === 'UNDER_REVIEW' && <p>Your request is with our review team. Submitted evidence cannot be changed.</p>}
    {data?.status === 'VERIFIED' && <p>Your seller verification is approved. Selling features are not available yet.</p>}
  </section>;
}

export default function SellerVerificationPage() {
  const version = useAuthStore((s) => s.sessionVersion);
  return <VerificationForm key={version} />;
}
