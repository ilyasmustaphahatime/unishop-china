import { apiClient } from '../../services/apiClient';
import { verificationSchema, validateEvidenceFile } from './schemas';
import type { EvidenceType } from './types';

export async function getVerification() {
  const response = await apiClient.get('/seller-verification/me');
  return verificationSchema.nullable().parse(response.data);
}

export async function changeVerification(action: 'start' | 'submit' | 'renew_challenge') {
  const response = await apiClient.post('/seller-verification', { action });
  return verificationSchema.parse(response.data);
}

export async function uploadEvidence(kind: EvidenceType, file: File, challenge?: string) {
  const error = validateEvidenceFile(file);
  if (error) throw new Error(error);
  const form = new FormData();
  form.append('evidence_type', kind);
  form.append('file', file);
  if (kind === 'HANDWRITTEN_CODE') {
    if (!challenge || !/^[A-F0-9]{12}$/.test(challenge)) throw new Error('Reload the current challenge.');
    form.append('challenge', challenge);
  }
  const response = await apiClient.post('/seller-verification/evidence', form, {
    headers: { 'Content-Type': undefined }, timeout: 45_000,
  });
  return verificationSchema.parse(response.data);
}
