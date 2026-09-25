import { z } from 'zod';

export const evidenceTypes = ['SELFIE', 'WECHAT_PROOF', 'HANDWRITTEN_CODE'] as const;
export const verificationSchema = z.object({
  review_reference: z.string().regex(/^[a-f0-9]{32}$/),
  status: z.enum(['PENDING', 'UNDER_REVIEW', 'VERIFIED', 'REJECTED']),
  handwritten_challenge: z.string().regex(/^[A-F0-9]{12}$/),
  rejection_reason: z.string().nullable(),
  submitted_at: z.string().nullable(),
  reviewed_at: z.string().nullable(),
  created_at: z.string(),
  evidence: z.array(z.object({
    evidence_type: z.enum(evidenceTypes),
    mime_type: z.enum(['image/jpeg', 'image/png']),
    size: z.number().int().positive().max(5 * 1024 * 1024),
  }).strict()).max(3),
}).strict();

export function validateEvidenceFile(file: File): string | null {
  if (!file.size || file.size > 5 * 1024 * 1024) return 'Choose an image no larger than 5 MiB.';
  if (!/^[A-Za-z0-9][A-Za-z0-9 _-]{0,110}\.(jpg|jpeg|png)$/i.test(file.name))
    return 'Use a simple JPEG or PNG filename.';
  const expected = file.name.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
  if (file.type !== expected) return 'Choose a JPEG or PNG image with a matching extension.';
  return null;
}
