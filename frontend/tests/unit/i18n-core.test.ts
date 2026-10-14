import { describe, expect, it, vi } from 'vitest';
import { i18n, currentLanguage } from '../../src/i18n';
import { createLanguageController } from '../../src/i18n/controller';
import { languages, isSupportedLanguage, supportedLanguages } from '../../src/i18n/languages';
import { localePreferenceKey, readLanguage, saveLanguage } from '../../src/i18n/persistence';
import { resources, namespaces } from '../../src/i18n/resources';
import { catalogName, formatCurrency, formatDate, formatListingTimestamp, formatNumber } from '../../src/i18n/formatters';
import { localizeMessage } from '../../src/i18n/messages';
import { createInstance } from 'i18next';

describe('locale registry and preferences', () => {
  it.each(['en', 'zh-CN', 'ar', 'fr'])('accepts only an approved locale: %s', (locale) => {
    expect(isSupportedLanguage(locale)).toBe(true);
    localStorage.setItem(localePreferenceKey, locale);
    expect(readLanguage()).toBe(locale);
  });
  it.each(['', 'en-US', 'AR', '../ar', '<script>alert(1)</script>', '__proto__', 'constructor', '\uD800', 'a'.repeat(10_000)])('rejects an invalid preference: %s', (value) => {
    localStorage.setItem(localePreferenceKey, value);
    expect(readLanguage()).toBe('en');
    expect(isSupportedLanguage(value)).toBe(false);
  });
  it.each([null, undefined, {}, { toString: () => 'ar' }, ['ar'], 0, true])('rejects non-string locale input', (value) => {
    expect(isSupportedLanguage(value)).toBe(false);
  });
  it('defaults to English with no preference', () => {
    localStorage.removeItem(localePreferenceKey);
    expect(readLanguage()).toBe('en');
  });
  it('tolerates blocked reads and writes', () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readLanguage()).toBe('en');
    get.mockRestore();
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(() => saveLanguage('ar')).not.toThrow();
    set.mockRestore();
  });
  it('writes only the language key and preserves unrelated storage', () => {
    localStorage.setItem('unrelated', 'keep');
    saveLanguage('ar');
    expect(localStorage.getItem('unrelated')).toBe('keep');
    expect(localStorage.getItem(localePreferenceKey)).toBe('ar');
    localStorage.removeItem('unrelated');
  });
});

describe('resources and formatting', () => {
  it.each(supportedLanguages)('does not tell users that implemented listings are unavailable: %s', (locale) => {
    const categoryCopy = resources[locale].catalog.directoryCopy;
    const approvalCopy = resources[locale].verification.approvedCopy;
    expect(categoryCopy).not.toMatch(/not available yet|尚未开放|غير متاحة بعد|ne sont pas encore disponibles/i);
    expect(approvalCopy).not.toMatch(/not available yet|尚未开放|غير متاحة بعد|ne sont pas encore disponibles/i);
  });
  it('does not advertise chat or in-app payment and delivery before those features exist', () => {
    expect(resources.en.auth.connectionCopy).not.toMatch(/chat safely|arrange payment and delivery/i);
    expect(resources['zh-CN'].auth.connectionCopy).not.toMatch(/安全交流|私下协商付款与交付/);
    expect(resources.ar.auth.connectionCopy).not.toMatch(/وتحادث بأمان|الدفع والتسليم بشكل خاص/);
    expect(resources.fr.auth.connectionCopy).not.toMatch(/discutez en sécurité|paiement et de la livraison en privé/i);
    expect(resources.en.auth.accessCopy).not.toMatch(/saved products|conversations|informal deals/i);
    expect(resources['zh-CN'].auth.accessCopy).not.toMatch(/已收藏商品|对话|私下交易/);
    expect(resources.ar.auth.accessCopy).not.toMatch(/منتجاتك المحفوظة|محادثاتك|اتفاقاتك غير الرسمية/);
    expect(resources.fr.auth.accessCopy).not.toMatch(/produits enregistrés|conversations|accords informels/i);
  });
  it('falls back to English if a local key is unavailable, independently of coverage checks', async () => {
    const isolated = createInstance();
    await isolated.init({ resources: { en: resources.en, ar: { common: { language: 'اللغة' } } }, lng: 'ar', fallbackLng: 'en', ns: [...namespaces], initAsync: false });
    expect(isolated.t('auth:loginTitle')).toBe(resources.en.auth.loginTitle);
  });
  it.each(supportedLanguages)('has complete semantic key/placeholder parity: %s', (locale) => {
    expect(Object.keys(resources[locale]).sort()).toEqual([...namespaces].sort());
    for (const ns of namespaces) {
      const base = resources.en[ns] as Record<string, string>;
      const values = resources[locale][ns] as Record<string, string>;
      const semantic = (key: string) => key.replace(/_(zero|one|two|few|many|other)$/, '');
      expect([...new Set(Object.keys(values).map(semantic))].sort()).toEqual([...new Set(Object.keys(base).map(semantic))].sort());
      for (const [key, value] of Object.entries(values)) {
        expect(value.trim()).not.toBe('');
        const reference = base[key] ?? base[semantic(key) + '_other'];
        const placeholders = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();
        expect(placeholders(value)).toEqual(placeholders(reference));
        if (key.endsWith('_other')) {
          for (const category of new Intl.PluralRules(languages[locale].intlLocale).resolvedOptions().pluralCategories) {
            expect(values[semantic(key) + '_' + category]).toBeTruthy();
          }
        }
      }
    }
  });
  it.each([0, 1, 2, 3, 5, 10, 11, 21, 100, 101, 102])('selects Arabic plural category for %i images/seconds', async (count) => {
    await i18n.changeLanguage('ar');
    const category = new Intl.PluralRules('ar').select(count);
    expect(i18n.t('products:imagesRemaining', { count })).toBe(resources.ar.products[`imagesRemaining_${category}` as keyof typeof resources.ar.products].replace('{{count}}', String(count)));
    expect(i18n.t('verification:expiresIn', { count })).not.toContain('{{');
  });
  it.each(supportedLanguages)('formats CNY, numbers and dates without modifying inputs: %s', (locale) => {
    const price = '1234.50';
    expect(formatCurrency(price, locale)).toBe(new Intl.NumberFormat(languages[locale].intlLocale, { style: 'currency', currency: 'CNY' }).format(1234.5));
    expect(price).toBe('1234.50');
    expect(formatNumber(1000, locale)).toBe(new Intl.NumberFormat(languages[locale].intlLocale).format(1000));
    const nearBoundary = '2026-10-13T23:59:59Z';
    expect(formatDate(nearBoundary, { dateStyle: 'medium' }, locale)).toBe(new Intl.DateTimeFormat(languages[locale].intlLocale, { dateStyle: 'medium' }).format(new Date(nearBoundary)));
    expect(formatDate('invalid', undefined, locale)).toBe('—');
    expect(formatDate(null, undefined, locale)).toBe('—');
    expect(formatCurrency('1,23', locale)).toBe('—');
  });
  it('uses only approved catalog names; Arabic/French fall back to English', () => {
    const city = { name_en: 'Beijing', name_zh: '北京' };
    expect(catalogName(city, 'zh-CN')).toBe('北京');
    expect(catalogName(city, 'ar')).toBe('Beijing');
    expect(catalogName(city, 'fr')).toBe('Beijing');
    expect(catalogName({ name_en: 'Beijing', name_zh: '' }, 'zh-CN')).toBe('Beijing');
  });
  it.each(supportedLanguages)('retains the listing UTC clock for zoned/naive MySQL timestamps: %s', (locale) => {
    const instant = '2026-10-13T23:59:59Z';
    const expected = new Intl.DateTimeFormat(languages[locale].intlLocale, {
      year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
      second: '2-digit', timeZone: 'UTC', timeZoneName: 'short',
    }).format(new Date(instant));
    expect(formatListingTimestamp(instant, locale)).toBe(expected);
    expect(formatListingTimestamp(instant.slice(0, -1), locale)).toBe(expected);
    expect(formatListingTimestamp('', locale)).toBe('—');
    expect(formatListingTimestamp('invalid', locale)).toBe('—');
  });
  it('hides unknown/raw server errors in every locale', async () => {
    for (const locale of supportedLanguages) {
      await i18n.changeLanguage(locale);
      for (const value of [
        'SQL /private/evidence secret-token',
        'C:\\private\\evidence\\object.jpg',
        'Bearer header.payload.signature',
        'Traceback (most recent call last): internal path',
        '<script>alert(1)</script>',
        { detail: 'internal storage_key' },
      ]) {
        expect(localizeMessage(value)).toBe(i18n.t('validation:unexpected'));
      }
    }
  });
  it('initializes once with locally bundled English fallback', async () => {
    expect(i18n.isInitialized).toBe(true);
    expect(i18n.options.fallbackLng).toEqual(['en']);
    expect(i18n.options.load).toBe('currentOnly');
    expect(i18n.options.saveMissing).toBe(false);
    await i18n.changeLanguage('fr');
    expect(currentLanguage()).toBe('fr');
    expect(document.documentElement.lang).toBe('fr');
    expect(document.documentElement.dir).toBe('ltr');
  });
});

describe('serialized language controller', () => {
  it('makes the latest rapid selection authoritative, without persisting stale choices', async () => {
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const changes: string[] = [];
    const engine = { changeLanguage: vi.fn(async (value?: string) => { changes.push(value!); if (value === 'ar') await blocked; return i18n.t; }) };
    const persist = vi.fn();
    const change = createLanguageController(engine, 'en', persist);
    const first = change('ar');
    await Promise.resolve();
    void change('fr');
    const last = change('zh-CN');
    release();
    expect(await first).toBe(true);
    expect(await last).toBe(true);
    expect(changes).toEqual(['ar', 'zh-CN']);
    expect(persist.mock.calls).toEqual([['zh-CN']]);
    expect(await change('../ar')).toBe(false);
  });
  it('recovers to the last committed language if a change fails', async () => {
    const engine = { changeLanguage: vi.fn(async (value?: string) => { if (value === 'ar') throw new Error('failure'); return i18n.t; }) };
    const persist = vi.fn();
    const change = createLanguageController(engine, 'en', persist);
    expect(await change('ar')).toBe(false);
    expect(engine.changeLanguage.mock.calls).toEqual([['ar'], ['en']]);
    expect(persist).not.toHaveBeenCalled();
  });
});
