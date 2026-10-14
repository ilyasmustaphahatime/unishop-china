import { i18n } from '../../src/i18n';
import type { MessageKey } from '../../src/i18n/resources';

// Compile-only fixtures: never imported into the runtime bundle.
export function checkTranslationTypes() {
  i18n.t('auth:loginTitle');
  i18n.t('products:imagesRemaining', { count: 2 });
  // @ts-expect-error Misspelled semantic keys must not compile.
  i18n.t('auth:logniTitle');
  // @ts-expect-error Unsupported namespace must not compile.
  i18n.t('payments:title');
  // @ts-expect-error A fallback string must not bypass strict key checking.
  i18n.t('auth:logniTitle', { defaultValue: 'Fallback' });
  const valid: MessageKey = 'validation:fieldInvalid';
  // @ts-expect-error Safe-message adapters accept only real semantic keys.
  const invalid: MessageKey = 'validation:unknownSecret';
  return [valid, invalid];
}
