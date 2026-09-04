import { z } from 'zod';
import { supportedCities } from './types';

const directionControls = new Set([0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069]);

function hasUnsafeControl(value: string, allowNewlines = false) {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    const allowedWhitespace = allowNewlines && (character === '\n' || character === '\t');
    return ((!allowedWhitespace && (codePoint < 32 || codePoint === 127)) || directionControls.has(codePoint));
  });
}

export const profileFormSchema = z.object({
  displayName: z
    .string()
    .trim()
    .min(2, 'Display name must contain at least 2 characters.')
    .max(50, 'Display name must contain at most 50 characters.')
    .refine((value) => !hasUnsafeControl(value), 'Display name contains unsupported characters.'),
  bio: z
    .string()
    .trim()
    .max(300, 'Bio must contain at most 300 characters.')
    .refine((value) => !hasUnsafeControl(value, true), 'Bio contains unsupported characters.'),
  city: z.enum(supportedCities, { error: 'Choose a supported city.' }),
});

export type ProfileFormValues = z.infer<typeof profileFormSchema>;
