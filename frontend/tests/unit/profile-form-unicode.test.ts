import { describe, expect, it } from 'vitest';
import { profileFormSchema } from '../../src/features/profiles/schemas';

const valid = { displayName: 'Example Name', bio: '', city: 'qingdao' };

describe('profile form matches server Unicode validation', () => {
  it('uses Unicode codepoints for minimum and maximum lengths', () => {
    expect(profileFormSchema.safeParse({ ...valid, displayName: '😀' }).success).toBe(false);
    expect(profileFormSchema.safeParse({ ...valid, displayName: '😀'.repeat(50) }).success).toBe(true);
    expect(profileFormSchema.safeParse({ ...valid, displayName: '😀'.repeat(51) }).success).toBe(false);
    expect(profileFormSchema.safeParse({ ...valid, bio: '😀'.repeat(300) }).success).toBe(true);
    expect(profileFormSchema.safeParse({ ...valid, bio: '😀'.repeat(301) }).success).toBe(false);
  });

  it('normalizes NFC before checking bounds and sending the request', () => {
    expect(profileFormSchema.parse({ ...valid, displayName: 'e\u0301'.repeat(50), bio: 'e\u0301'.repeat(300) }))
      .toEqual({ ...valid, displayName: 'é'.repeat(50), bio: 'é'.repeat(300) });
  });

  it.each(['\u0080', '\u009f', '\ud800', '\udfff', '\u202e', '\u2067'])('rejects unsupported controls or surrogates', (character) => {
    expect(profileFormSchema.safeParse({ ...valid, displayName: `Ab${character}cd` }).success).toBe(false);
    expect(profileFormSchema.safeParse({ ...valid, bio: `Ab${character}cd` }).success).toBe(false);
  });

  it('permits embedded newlines and tabs only in bio', () => {
    expect(profileFormSchema.safeParse({ ...valid, bio: 'First\n\tSecond' }).success).toBe(true);
    expect(profileFormSchema.safeParse({ ...valid, displayName: 'First\nSecond' }).success).toBe(false);
  });
});
