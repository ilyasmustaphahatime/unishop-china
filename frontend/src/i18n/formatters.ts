import { currentLanguage } from './index';
import { languages, type SupportedLanguage } from './languages';

export function formatNumber(value: number, locale: SupportedLanguage = currentLanguage()): string {
  return Number.isFinite(value) ? new Intl.NumberFormat(languages[locale].intlLocale).format(value) : '—';
}
export function formatCurrency(value: string, locale: SupportedLanguage = currentLanguage()): string {
  // Display only. Never use this formatted/Number value for API input or arithmetic.
  if (!/^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/.test(value)) return '—';
  return new Intl.NumberFormat(languages[locale].intlLocale, { style: 'currency', currency: 'CNY' }).format(Number(value));
}
export function formatDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }, locale: SupportedLanguage = currentLanguage()): string {
  if (!value) return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '—';
  // Default to existing browser-local semantics; the listing helper retains UTC explicitly.
  return new Intl.DateTimeFormat(languages[locale].intlLocale, options).format(date);
}
export function formatListingTimestamp(value: string, locale: SupportedLanguage = currentLanguage()): string {
  // MySQL DATETIME values are UTC (backend/app/models/base.py). Owner lists used to
  // show the original ISO clock; do not shift it to the browser's timezone.
  const timestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? value + 'Z' : value;
  return formatDate(timestamp, {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    second: '2-digit', timeZone: 'UTC', timeZoneName: 'short',
  }, locale);
}
export function catalogName(value: { name_en: string; name_zh?: string | null }, locale: SupportedLanguage = currentLanguage()): string {
  return value[languages[locale].catalogName] || value.name_en;
}
