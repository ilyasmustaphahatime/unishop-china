import { describe, expect, it } from 'vitest';
import { myProfileApiSchema, publicProfileApiSchema } from '../../src/features/profiles/contracts';

const base = {
  public_id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Profile Person',
  bio: null,
  city: 'Qingdao',
  member_since: '2026-01-01T00:00:00',
  email_verified: true,
  phone_verified: false,
};

describe('profile API contracts', () => {
  it('accepts MySQL-backed timestamp strings without weakening field strictness', () => {
    expect(
      myProfileApiSchema.parse({
        ...base,
        onboarding_completed: true,
        created_at: '2026-09-04T00:00:00',
        updated_at: '2026-09-04T00:00:00',
      }).onboarding_completed,
    ).toBe(true);
  });

  it.each(['email', 'phone_number', 'user_id', 'account_status', 'roles', 'password_hash'])(
    'rejects leaked public field %s',
    (field) => {
      expect(publicProfileApiSchema.safeParse({ ...base, [field]: 'leaked' }).success).toBe(false);
    },
  );
});
