import l0common from './locales/en/common.json';
import l0auth from './locales/en/auth.json';
import l0profile from './locales/en/profile.json';
import l0catalog from './locales/en/catalog.json';
import l0products from './locales/en/products.json';
import l0verification from './locales/en/verification.json';
import l0validation from './locales/en/validation.json';
import l1common from './locales/zh-CN/common.json';
import l1auth from './locales/zh-CN/auth.json';
import l1profile from './locales/zh-CN/profile.json';
import l1catalog from './locales/zh-CN/catalog.json';
import l1products from './locales/zh-CN/products.json';
import l1verification from './locales/zh-CN/verification.json';
import l1validation from './locales/zh-CN/validation.json';
import l2common from './locales/ar/common.json';
import l2auth from './locales/ar/auth.json';
import l2profile from './locales/ar/profile.json';
import l2catalog from './locales/ar/catalog.json';
import l2products from './locales/ar/products.json';
import l2verification from './locales/ar/verification.json';
import l2validation from './locales/ar/validation.json';
import l3common from './locales/fr/common.json';
import l3auth from './locales/fr/auth.json';
import l3profile from './locales/fr/profile.json';
import l3catalog from './locales/fr/catalog.json';
import l3products from './locales/fr/products.json';
import l3verification from './locales/fr/verification.json';
import l3validation from './locales/fr/validation.json';

export const namespaces = ['common', 'auth', 'profile', 'verification', 'products', 'catalog', 'validation'] as const;
export const resources = {
  'en': { common: l0common, auth: l0auth, profile: l0profile, catalog: l0catalog, products: l0products, verification: l0verification, validation: l0validation },
  'zh-CN': { common: l1common, auth: l1auth, profile: l1profile, catalog: l1catalog, products: l1products, verification: l1verification, validation: l1validation },
  'ar': { common: l2common, auth: l2auth, profile: l2profile, catalog: l2catalog, products: l2products, verification: l2verification, validation: l2validation },
  'fr': { common: l3common, auth: l3auth, profile: l3profile, catalog: l3catalog, products: l3products, verification: l3verification, validation: l3validation },
} as const;
export type TranslationResources = typeof resources.en;
export type MessageKey = { [N in keyof TranslationResources]: `${N}:${keyof TranslationResources[N] & string}` }[keyof TranslationResources];
