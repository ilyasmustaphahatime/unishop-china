import { apiClient } from '../../services/apiClient';
import { myProfileApiSchema, publicProfileApiSchema } from './contracts';
import { normalizePublicHandle } from './handles';
import type { MyProfile, PublicProfile, UpdateProfileInput } from './types';

function mapMyProfile(data: ReturnType<typeof myProfileApiSchema.parse>): MyProfile {
  return {
    publicHandle: data.public_handle,
    displayName: data.display_name,
    bio: data.bio,
    city: data.city,
    onboardingCompleted: data.onboarding_completed,
    memberSince: data.member_since,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
    emailVerified: data.email_verified,
    phoneVerified: data.phone_verified,
  };
}

export async function getMyProfile(): Promise<MyProfile> {
  const response = await apiClient.get('/profile/me');
  return mapMyProfile(myProfileApiSchema.parse(response.data));
}

export async function updateMyProfile(input: UpdateProfileInput): Promise<MyProfile> {
  const payload: Record<string, string | null> = {};
  if ('displayName' in input) payload.display_name = input.displayName ?? null;
  if ('bio' in input) payload.bio = input.bio ?? null;
  if ('city' in input) payload.city = input.city ?? null;
  const response = await apiClient.patch('/profile/me', payload);
  return mapMyProfile(myProfileApiSchema.parse(response.data));
}

export async function completeOnboarding(): Promise<MyProfile> {
  const response = await apiClient.post('/profile/onboarding/complete', {});
  return mapMyProfile(myProfileApiSchema.parse(response.data));
}

export async function getPublicProfile(publicHandle: string): Promise<PublicProfile> {
  const handle = normalizePublicHandle(publicHandle);
  if (!handle) throw new Error('Profile not found.');
  const response = await apiClient.get(`/profiles/by-handle/${handle}`);
  const data = publicProfileApiSchema.parse(response.data);
  return {
    publicHandle: data.public_handle,
    displayName: data.display_name,
    bio: data.bio,
    city: data.city,
    memberSince: data.member_since,
    emailVerified: data.email_verified,
    phoneVerified: data.phone_verified,
  };
}
