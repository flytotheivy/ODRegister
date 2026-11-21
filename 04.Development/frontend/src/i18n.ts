import { en, type Messages } from './locales/en.ts';
import { srLatn } from './locales/sr-Latn.ts';
import { srCyrl } from './locales/sr-Cyrl.ts';
export const locales = ['en', 'sr-Latn', 'sr-Cyrl'] as const;
export type Locale = typeof locales[number];
export const dictionaries: Record<Locale, Messages> = { en, 'sr-Latn': srLatn, 'sr-Cyrl': srCyrl };
export function resolveLocale(value: string | null): Locale {
  return locales.includes(value as Locale) ? value as Locale : 'en';
}
