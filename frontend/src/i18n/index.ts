import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';
import { defaultLanguage, isSupportedLanguage, languages, supportedLanguages } from './languages';
import { readLanguage } from './persistence';
import { namespaces, resources } from './resources';

// Locally bundled resources allow synchronous initialization before React renders.
// No detector, remote resource loader, auth provider or query client dependency.
export const i18n = i18next.createInstance();
void i18n.use(initReactI18next).init({
  resources,
  lng: readLanguage(),
  fallbackLng: defaultLanguage,
  supportedLngs: supportedLanguages,
  load: 'currentOnly',
  ns: [...namespaces],
  defaultNS: 'common',
  initAsync: false,
  returnNull: false,
  saveMissing: false,
  interpolation: { escapeValue: false }, // React escapes text; never inject translation HTML.
  react: { useSuspense: false },
});

export function currentLanguage() {
  return isSupportedLanguage(i18n.resolvedLanguage) ? i18n.resolvedLanguage : defaultLanguage;
}
export function syncDocument(): void {
  if (typeof document === 'undefined') return;
  const locale = currentLanguage();
  document.documentElement.lang = locale;
  document.documentElement.dir = languages[locale].direction;
  document.title = i18n.t('common:documentTitle');
  document.querySelector('meta[name="description"]')?.setAttribute('content', i18n.t('common:documentDescription'));
}
i18n.on('languageChanged', syncDocument);
syncDocument();
