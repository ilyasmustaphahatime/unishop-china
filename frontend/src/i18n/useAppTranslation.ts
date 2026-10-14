import { useTranslation } from 'react-i18next';
import { i18n, currentLanguage } from './index';
import { namespaces } from './resources';

export function useAppTranslation() {
  const translation = useTranslation(namespaces, { i18n });
  return { ...translation, locale: currentLanguage() };
}
