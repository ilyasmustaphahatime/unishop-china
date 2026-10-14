import { defaultLanguage, isSupportedLanguage, type SupportedLanguage } from './languages';

export const localePreferenceKey = 'unishop.locale';
export function readLanguage(): SupportedLanguage {
  try {
    const saved = window.localStorage.getItem(localePreferenceKey);
    return isSupportedLanguage(saved) ? saved : defaultLanguage;
  } catch { return defaultLanguage; }
}
export function saveLanguage(language: SupportedLanguage): void {
  if (!isSupportedLanguage(language)) return;
  try { window.localStorage.setItem(localePreferenceKey, language); }
  catch { /* A blocked preference store must not block presentation. */ }
}
