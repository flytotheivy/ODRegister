import type {Locale} from './i18n';
import {dictionaries,locales} from './i18n';
import {useEffect,useId,useState} from 'react';
import {authFetch,profile,type Profile} from './authApi';
export const uiMessages={
 en:{home:'Overview',plans:'Annual plans',access:'Request access',status:'Request status',login:'Sign in',account:'My account',workspace:'My plans',navigation:'Main navigation',menu:'Menu',progress:'Annual progress',accounts:'Accounts',register:'Institutions',data:'Data exports',settings:'Settings',statistics:'Published data',scope:'Submitted plans only. Drafts and account information are private.',themes:'Datasets by theme',plansCount:'Submitted plans',datasets:'Dataset items',institutions:'Institutions',empty:'No published datasets yet.',failed:'Statistics could not be loaded.',retry:'Retry',loading:'Loading statistics…',table:'View data table',quarter:'Planned publication quarter',unspecified:'Not specified',share:'Share of dataset items'},
 'sr-Latn':{home:'Pregled',plans:'Godišnji planovi',access:'Zatraži pristup',status:'Status zahteva',login:'Prijava',account:'Moj nalog',workspace:'Moji planovi',navigation:'Glavna navigacija',menu:'Meni',progress:'Godišnji napredak',accounts:'Nalozi',register:'Institucije',data:'Izvoz podataka',settings:'Podešavanja',statistics:'Objavljeni podaci',scope:'Samo podneti planovi. Nacrti i podaci o nalozima su privatni.',themes:'Skupovi podataka po temi',plansCount:'Podneti planovi',datasets:'Stavke skupova podataka',institutions:'Institucije',empty:'Još nema objavljenih skupova podataka.',failed:'Statistika nije učitana.',retry:'Pokušaj ponovo',loading:'Učitavanje statistike…',table:'Prikaži tabelu',quarter:'Planirani kvartal objavljivanja',unspecified:'Nije navedeno',share:'Udeo stavki skupova podataka'},
 'sr-Cyrl':{home:'Преглед',plans:'Годишњи планови',access:'Затражи приступ',status:'Статус захтева',login:'Пријава',account:'Мој налог',workspace:'Моји планови',navigation:'Главна навигација',menu:'Мени',progress:'Годишњи напредак',accounts:'Налози',register:'Институције',data:'Извоз података',settings:'Подешавања',statistics:'Објављени подаци',scope:'Само поднети планови. Нацрти и подаци о налозима су приватни.',themes:'Скупови података по теми',plansCount:'Поднети планови',datasets:'Ставке скупова података',institutions:'Институције',empty:'Још нема објављених скупова података.',failed:'Статистика није учитана.',retry:'Покушај поново',loading:'Учитавање статистике…',table:'Прикажи табелу',quarter:'Планирани квартал објављивања',unspecified:'Није наведено',share:'Удео ставки скупова података'}
};
/* 공통 골격 문구(EDS 상단 띠·푸터). 세르비아어는 원어민 검수 필요 */
export const shellMessages={
 en:{gov:'Republic of Serbia',service:'Annual publication plans',menu:'Menu',close:'Close menu',admin:'Administrator',publicView:'Public site',footerAbout:'Institutions register the datasets they plan to publish each year. Submitted plans are open to everyone.',footerPublic:'Public information',footerInstitutions:'For institutions',json:'Annual plans and JSON download'},
 'sr-Latn':{gov:'Republika Srbija',service:'Godišnji planovi objavljivanja',menu:'Meni',close:'Zatvori meni',admin:'Administrator',publicView:'Javni prikaz',footerAbout:'Institucije svake godine prijavljuju skupove podataka koje planiraju da objave. Podneti planovi su dostupni svima.',footerPublic:'Javne informacije',footerInstitutions:'Za institucije',json:'Godišnji planovi i JSON preuzimanje'},
 'sr-Cyrl':{gov:'Република Србија',service:'Годишњи планови објављивања',menu:'Мени',close:'Затвори мени',admin:'Администратор',publicView:'Јавни приказ',footerAbout:'Институције сваке године пријављују скупове података које планирају да објаве. Поднети планови су доступни свима.',footerPublic:'Јавне информације',footerInstitutions:'За институције',json:'Годишњи планови и JSON преузимање'}
} as const;
const languageLabel=(l:Locale)=>l==='en'?'EN':l==='sr-Latn'?'LAT':'ЋИР';
const languageName=(l:Locale)=>l==='en'?'English':l==='sr-Latn'?'Srpski (latinica)':'Српски (ћирилица)';
function isCurrent(path:string){const p=location.pathname;if(path==='/')return p==='/';if(path==='/plans')return p.startsWith('/plans');if(path==='/my-plans')return p==='/my-plans'||p.startsWith('/my-plans/');return p===path;}
export default function SiteHeader({locale,onLocale,context}:{locale:Locale;onLocale:(l:Locale)=>void;context?:Profile|null}){
 const [detected,setDetected]=useState<Profile|null>(null);
 const [open,setOpen]=useState(false);
 const navId=useId();
 useEffect(()=>{if(context!==undefined)return;const c=new AbortController();void authFetch('auth/me',undefined,undefined,c.signal).then(v=>{if(!c.signal.aborted)setDetected(profile(v));}).catch(()=>{if(!c.signal.aborted)setDetected(null);});return()=>c.abort();},[context]);
 const actor=context===undefined?detected:context,t=uiMessages[locale],s=shellMessages[locale],b=dictionaries[locale],admin=!!actor&&actor.role!=='institution_user';
 const links:([string,string])[]=admin
  ?[[t.progress,'/admin'],[t.accounts,'/admin/accounts'],[t.register,'/admin/institutions'],[t.data,'/admin/datasets'],[t.settings,'/admin/settings']]
  :actor?[[t.workspace,'/my-plans'],[t.plans,'/plans'],[t.home,'/']]
  :[[t.home,'/'],[t.plans,'/plans'],[t.access,'/account/request'],[t.status,'/account/status']];
 const q='?lang='+locale;
 return <div className="masthead">
  <div className="topbar"><div className="container topbar-inner">
   <span className="topbar-gov"><span className="serbia-mark" aria-hidden="true"><i/><i/><i/></span><span className="topbar-text">{s.gov}</span></span>
   <nav className="languages" aria-label={b.language}>{locales.map(l=><button type="button" key={l} lang={l} aria-pressed={locale===l} aria-label={languageName(l)} onClick={()=>onLocale(l)}>{languageLabel(l)}</button>)}</nav>
  </div></div>
  <header className={'site-header'+(admin?' is-admin':'')}><div className="container header-inner">
   <a className="brand" href={(admin?'/admin':'/')+q}><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><span className="brand-text"><strong>{b.brand}</strong><small>{s.service}</small></span></a>
   <button type="button" className="menu-toggle button-outline" aria-expanded={open} aria-controls={navId} onClick={()=>setOpen(v=>!v)}>{open?s.close:s.menu}</button>
   <nav id={navId} className={'primary-nav'+(open?' is-open':'')} aria-label={t.navigation}>{links.map(([label,path])=><a key={path} href={path+q} aria-current={isCurrent(path)?'page':undefined}>{label}</a>)}</nav>
   <div className="header-account">
    {admin&&<a className="button-text" href={'/'+q}>{s.publicView}</a>}
    {actor
     ?<a className="account-link" href={'/sign-in'+q} aria-current={isCurrent('/sign-in')?'page':undefined}><svg className="account-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-3.3 0-8 1.7-8 5v1h16v-1c0-3.3-4.7-5-8-5z"/></svg>{admin&&<span className="role-tag">{s.admin}</span>}<span className="account-name">{actor.name||t.account}</span></a>
     :<a className="button-link" href={'/sign-in'+q} aria-current={isCurrent('/sign-in')?'page':undefined}>{t.login}</a>}
   </div>
  </div></header>
 </div>;
}
export function SiteFooter({locale}:{locale:Locale}){
 const t=uiMessages[locale],s=shellMessages[locale],b=dictionaries[locale],q='?lang='+locale;
 return <footer className="site-footer">
  <div className="container footer-main">
   <div className="footer-brand"><a className="brand" href={'/'+q}><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><span className="brand-text"><strong>{b.brand}</strong><small>{s.service}</small></span></a><p>{s.footerAbout}</p></div>
   <div><h2>{s.footerPublic}</h2><ul><li><a href={'/'+q}>{t.home}</a></li><li><a href={'/plans'+q}>{s.json}</a></li></ul></div>
   <div><h2>{s.footerInstitutions}</h2><ul><li><a href={'/account/request'+q}>{t.access}</a></li><li><a href={'/account/status'+q}>{t.status}</a></li><li><a href={'/sign-in'+q}>{t.login}</a></li></ul></div>
  </div>
  <div className="container"><div className="footer-legal"><span>{s.gov}</span><span>{b.footer} · {b.draft}</span></div></div>
 </footer>;
}
