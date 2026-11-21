import type {Locale} from './i18n';
import {cyclesMessages} from './cyclesMessages';
export default function SettingsNav({locale,section}:{locale:Locale;section:'cycles'|'themes'|'domains'}){const t=cyclesMessages[locale];return <nav className="settings-nav" aria-label={t.title}>{(['cycles','themes','domains'] as const).map(s=><a key={s} href={'/admin/settings?lang='+locale+(s==='domains'?'':'&section='+s)} aria-current={section===s?'page':undefined}>{t[s]}</a>)}</nav>;}
