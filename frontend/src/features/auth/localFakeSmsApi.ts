import axios from 'axios';
import { apiClient } from '../../services/apiClient';

export type FakeSmsMessage = {
  messageId: string;
  phoneNumberMasked: string;
  code: string;
  deliveryType: 'registration' | 'resend';
  createdAt: string;
  expiresAt: string;
  expiresInSeconds: number;
};

export type VerificationResult = { phoneVerified: true };

export type LocalFakeSmsApi = {
  register(phoneNumber: string, password: string): Promise<void>;
  resend(phoneNumber: string): Promise<void>;
  latest(phoneNumber: string, signal: AbortSignal): Promise<FakeSmsMessage | null>;
  verify(phoneNumber: string, code: string): Promise<VerificationResult>;
  consume(messageId: string): Promise<void>;
};

type ApiErrorPayload = { detail?: { code?: string } };

const safeMessages: Record<string, string> = {
  EMAIL_ALREADY_REGISTERED: 'This account already exists.',
  PHONE_ALREADY_REGISTERED: 'This phone number is already registered.',
  VERIFICATION_CODE_RATE_LIMITED: 'Please wait before requesting another code.',
  INVALID_VERIFICATION_CODE: 'The verification code is incorrect.',
  VERIFICATION_CODE_EXPIRED: 'The verification code has expired.',
  VERIFICATION_ATTEMPTS_EXCEEDED: 'Too many incorrect attempts. Request a new code.',
  SMS_PROVIDER_UNAVAILABLE: 'The local fake SMS service is unavailable.',
};

export class SafeLocalApiError extends Error {
  constructor(public readonly userMessage: string) {
    super(userMessage);
  }
}

function safeError(error: unknown): SafeLocalApiError {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    const code = error.response?.data?.detail?.code;
    if (code && safeMessages[code]) return new SafeLocalApiError(safeMessages[code]);
    if (!error.response) return new SafeLocalApiError('The backend is unavailable.');
  }
  return new SafeLocalApiError('The request could not be completed.');
}

function parseMessage(value: unknown): FakeSmsMessage {
  if (!value || typeof value !== 'object') {
    throw new SafeLocalApiError('The fake SMS response was invalid.');
  }
  const data = value as Record<string, unknown>;
  if (
    typeof data.message_id !== 'string' ||
    typeof data.phone_number_masked !== 'string' ||
    typeof data.code !== 'string' ||
    !/^[0-9]{6}$/.test(data.code) ||
    (data.delivery_type !== 'registration' && data.delivery_type !== 'resend') ||
    typeof data.created_at !== 'string' ||
    typeof data.expires_at !== 'string' ||
    typeof data.expires_in_seconds !== 'number'
  ) {
    throw new SafeLocalApiError('The fake SMS response was invalid.');
  }
  return {
    messageId: data.message_id,
    phoneNumberMasked: data.phone_number_masked,
    code: data.code,
    deliveryType: data.delivery_type,
    createdAt: data.created_at,
    expiresAt: data.expires_at,
    expiresInSeconds: data.expires_in_seconds,
  };
}

export const localFakeSmsApi: LocalFakeSmsApi = {
  async register(phoneNumber, password) {
    try {
      await apiClient.post('/auth/register', { phone_number: phoneNumber, password });
    } catch (error) {
      throw safeError(error);
    }
  },
  async resend(phoneNumber) {
    try {
      await apiClient.post('/auth/phone/resend-code', { phone_number: phoneNumber });
    } catch (error) {
      throw safeError(error);
    }
  },
  async latest(phoneNumber, signal) {
    try {
      const response = await apiClient.get('/dev/fake-sms/latest', {
        params: { phone_number: phoneNumber },
        signal,
      });
      return parseMessage(response.data);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) return null;
      throw safeError(error);
    }
  },
  async verify(phoneNumber, code) {
    try {
      const response = await apiClient.post('/auth/phone/verify', {
        phone_number: phoneNumber,
        code,
      });
      if (response.data?.phone_verified !== true) {
        throw new SafeLocalApiError('The verification response was invalid.');
      }
      return { phoneVerified: true };
    } catch (error) {
      if (error instanceof SafeLocalApiError) throw error;
      throw safeError(error);
    }
  },
  async consume(messageId) {
    try {
      await apiClient.delete(`/dev/fake-sms/${encodeURIComponent(messageId)}`);
    } catch {
      // Database verification already committed; server-side consumption is primary.
    }
  },
};
