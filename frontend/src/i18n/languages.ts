export const languages = {
  en: { nativeName: 'English', direction: 'ltr', intlLocale: 'en-US', catalogName: 'name_en' },
  'zh-CN': { nativeName: '简体中文', direction: 'ltr', intlLocale: 'zh-CN', catalogName: 'name_zh' },
  ar: { nativeName: 'العربية', direction: 'rtl', intlLocale: 'ar-MA', catalogName: 'name_en' },
  fr: { nativeName: 'Français', direction: 'ltr', intlLocale: 'fr-FR', catalogName: 'name_en' },
} as const;
export type SupportedLanguage = keyof typeof languages;
export const supportedLanguages = Object.keys(languages) as SupportedLanguage[];
export const defaultLanguage: SupportedLanguage = 'en';
export function isSupportedLanguage(value: unknown): value is SupportedLanguage {
  return typeof value === 'string' && Object.hasOwn(languages, value);
}
