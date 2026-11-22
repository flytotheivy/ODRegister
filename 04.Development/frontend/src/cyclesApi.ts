import {AuthError} from './authApi.ts';
export type Theme={id:string;code:string;uri:string;labels:Record<'en'|'sr-Latn'|'sr-Cyrl',string>;baseline:boolean;active?:boolean};
export type Cycle={id:string;year:number;opens_at:string;closes_at:string;timezone:string;licence_text:string;licence_url:string;revision:number;server_now:string;window_state:'scheduled'|'open'|'closed'};
export type CycleDetail=Cycle&{has_plans:boolean;institution_count:number;themes:Theme[]};
export type CyclePage={items:Cycle[];next_cursor:number|null;active_register_count:number};
const uuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
function validCycle(v:unknown):v is Cycle{const c=v as Cycle;return !!c&&uuid(c.id)&&Number.isInteger(c.year)&&c.year>=2000&&c.year<=9999&&Number.isSafeInteger(c.revision)&&c.revision>0&&['opens_at','closes_at','server_now'].every(k=>typeof c[k as keyof Cycle]==='string'&&Number.isFinite(Date.parse(c[k as keyof Cycle] as string)))&&typeof c.timezone==='string'&&typeof c.licence_text==='string'&&typeof c.licence_url==='string'&&['scheduled','open','closed'].includes(c.window_state);}
function validTheme(v:unknown):v is Theme{const t=v as Theme;return !!t&&uuid(t.id)&&typeof t.code==='string'&&typeof t.uri==='string'&&typeof t.baseline==='boolean'&&!!t.labels&&['en','sr-Latn','sr-Cyrl'].every(k=>typeof t.labels[k as keyof Theme['labels']]==='string'&&t.labels[k as keyof Theme['labels']].trim())&&(t.active===undefined||typeof t.active==='boolean');}
export function cyclePage(v:unknown):CyclePage{const x=v as CyclePage;if(!x||!Array.isArray(x.items)||!x.items.every(validCycle)||!Number.isSafeInteger(x.active_register_count)||x.active_register_count<0||(x.next_cursor!==null&&!Number.isInteger(x.next_cursor)))throw new AuthError('SERVICE_UNAVAILABLE');return x;}
export function cycleDetail(v:unknown):CycleDetail{const x=v as CycleDetail;if(!validCycle(x)||typeof x.has_plans!=='boolean'||!Number.isInteger(x.institution_count)||x.institution_count<0||!Array.isArray(x.themes)||!x.themes.every(t=>validTheme(t)&&typeof t.active==='boolean'))throw new AuthError('SERVICE_UNAVAILABLE');return x;}
export function themeCatalogue(v:unknown):Theme[]{const x=v as {items:Theme[]};if(!x||!Array.isArray(x.items)||!x.items.every(validTheme))throw new AuthError('SERVICE_UNAVAILABLE');return x.items;}
export const SERVICE_TIME_ZONE='Europe/Belgrade';
const STAMP_OPTIONS:Intl.DateTimeFormatOptions={day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'short'};
export function displayInstant(value:string,zone:string,locale:string){try{return new Intl.DateTimeFormat(locale==='en'?'en-GB':locale,{...STAMP_OPTIONS,timeZone:zone}).format(new Date(value));}catch{return value+' ('+zone+')';}}
export function displayStamp(value:string,locale:string){return displayInstant(value,SERVICE_TIME_ZONE,locale);}
