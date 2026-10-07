import { describe, expect, it } from 'vitest';
import { myProfileApiSchema, publicProfileApiSchema } from '../../src/features/profiles/contracts';

const base = {
  public_handle: 'user-a1b2c3d4',
  display_name: 'Profile Person',
  bio: null,
  city: 'Qingdao',
  member_since: '2026-01-01T00:00:00',
  email_verified: true,
  phone_verified: false,
};

describe('profile API contracts', () => {
  it('requires a boolean seller indicator without exposing verification details', () => {
    expect(publicProfileApiSchema.parse({ ...base, seller_verified: true }).seller_verified).toBe(true);
    expect(publicProfileApiSchema.safeParse({ ...base, seller_verified: 'VERIFIED' }).success).toBe(false);
    expect(publicProfileApiSchema.safeParse({ ...base, seller_verified: true, evidence: [] }).success).toBe(false);
  });
  it('accepts MySQL-backed timestamp strings without weakening field strictness', () => {
    expect(
      myProfileApiSchema.parse({
        ...base,
        city_slug: 'qingdao',
        city_active: true,
        onboarding_completed: true,
        created_at: '2026-09-04T00:00:00',
        updated_at: '2026-09-04T00:00:00',
      }).onboarding_completed,
    ).toBe(true);
  });

  it.each(['email', 'phone_number', 'user_id', 'account_status', 'roles', 'password_hash'])(
    'rejects leaked public field %s',
    (field) => {
      expect(publicProfileApiSchema.safeParse({ ...base, seller_verified: false, [field]: 'leaked' }).success).toBe(false);
    },
  );
});
