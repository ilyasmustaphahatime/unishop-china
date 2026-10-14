import type { i18n as I18n } from 'i18next';
import { i18n, currentLanguage } from './index';
import { isSupportedLanguage, type SupportedLanguage } from './languages';
import { saveLanguage } from './persistence';

// Serialize engine transitions: an older async completion can never win last.
// Persistence only follows the latest successful request. No auth/cache effects.
export function createLanguageController(
  engine: Pick<I18n, 'changeLanguage'>,
  initial: SupportedLanguage,
  persist: (language: SupportedLanguage) => void,
) {
  let committed = initial;
  let sequence = 0;
  let queue = Promise.resolve(true);
  return (value: unknown): Promise<boolean> => {
    if (!isSupportedLanguage(value)) return Promise.resolve(false);
    const ticket = ++sequence;
    queue = queue.then(async () => {
      if (ticket !== sequence) return true;
      try {
        await engine.changeLanguage(value);
        if (ticket === sequence) { committed = value; persist(value); }
        return true;
      } catch {
        // Roll back to the last successful presentation, not a raw saved value.
        await engine.changeLanguage(committed);
        return false;
      }
    }).catch(() => false);
    return queue;
  };
}
export const changeLanguage = createLanguageController(i18n, currentLanguage(), saveLanguage);
