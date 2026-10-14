import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';
import { i18n } from '../src/i18n';
import { localePreferenceKey } from '../src/i18n/persistence';

beforeEach(async () => {
  await i18n.changeLanguage('en');
  localStorage.removeItem(localePreferenceKey);
});

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
  localStorage.removeItem(localePreferenceKey);
});
