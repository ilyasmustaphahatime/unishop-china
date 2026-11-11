import { z } from 'zod';
import { catalogSlugSchema } from '../catalog/slugs';

const directionControls = new Set([0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069]);

function hasUnsafeControl(value: string, allowNewlines = false) {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    const allowedWhitespace = allowNewlines && (character === '\n' || character === '\t');
    return ((!allowedWhitespace && (codePoint < 32 || (codePoint >= 127 && codePoint <= 159)))
      || (codePoint >= 0xd800 && codePoint <= 0xdfff) || directionControls.has(codePoint));
  });
}

export const profileFormSchema = z.object({
  displayName: z
    .string()
    .transform((value) => value.normalize('NFC').trim())
    .refine((value) => Array.from(value).length >= 2, 'Display name must contain at least 2 characters.')
    .refine((value) => Array.from(value).length <= 50, 'Display name must contain at most 50 characters.')
    .refine((value) => !hasUnsafeControl(value), 'Display name contains unsupported characters.'),
  bio: z
    .string()
    .transform((value) => value.normalize('NFC').trim())
    .refine((value) => Array.from(value).length <= 300, 'Bio must contain at most 300 characters.')
    .refine((value) => !hasUnsafeControl(value, true), 'Bio contains unsupported characters.'),
  city: catalogSlugSchema,
});

export type ProfileFormValues = z.infer<typeof profileFormSchema>;
