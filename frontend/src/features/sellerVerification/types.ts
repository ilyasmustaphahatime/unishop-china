import type { z } from 'zod';
import type { verificationSchema, evidenceTypes } from './schemas';
export type SellerVerification = z.infer<typeof verificationSchema>;
export type EvidenceType = typeof evidenceTypes[number];
