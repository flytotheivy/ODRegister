import {useEffect, useRef, useState, type FormEvent} from 'react';
import {accessFetch, AccessError, institutionList, requestStatus, type Institution, type RequestStatus} from './accessApi';
import {accessMessages} from './accessMessages';
import {dictionaries, locales, resolveLocale, type Locale} from './i18n';
import './style.css';
import {authMessages} from './authMessages';
const languageNames: Record<Locale,string> = {en:'English', 'sr-Latn':'Srpski (latinica)', 'sr-Cyrl':'Српски (ћирилица)'};
export default function Access() {
 const [locale, setLocale] = useState<Locale>(()=>resolveLocale(new URLSearchParams(location.search).get('lang')));
 const [mode, setMode] = useState(location.pathname === '/account/status' ? 'status' : 'request');
 const [items, setItems] = useState<Institution[]>([]), [more,setMore] = useState(false), [selection,setSelection] = useState('');
 const [listState,setListState] = useState('loading'), [busy,setBusy] = useState(false), [error,setError] = useState('');
 const [result,setResult] = useState<RequestStatus | null>(null);
 const searchRef = useRef<HTMLInputElement>(null), resultRef = useRef<HTMLHeadingElement>(null);
 const searchAbort = useRef<AbortController | null>(null), sendAbort = useRef<AbortController | null>(null), sending = useRef(false);
 const t = accessMessages[locale], base = dictionaries[locale];
 const url = (path:string) => `${path}?lang=${locale}`;
 async function search(q:string) {
  searchAbort.current?.abort(); const controller = new AbortController(); searchAbort.current=controller;
  setListState('loading'); setSelection(''); setItems([]);
  const timer=setTimeout(()=>controller.abort(),10000);
  try {const data=institutionList(await accessFetch('institutions?q='+encodeURIComponent(q), controller.signal)); if(searchAbort.current===controller) {setItems(data.items);setMore(data.has_more);setListState('ready');}}
  catch {if(searchAbort.current===controller) setListState('error');}
  finally {clearTimeout(timer);}
 }
 useEffect(()=>{if(mode==='request') void search(''); return()=>{searchAbort.current?.abort(); searchAbort.current=null;sendAbort.current?.abort();};},[mode]);
 useEffect(()=>{document.documentElement.lang=locale;document.title=(mode==='request'?t.requestTitle:t.statusTitle)+' · '+base.brand;const next=new URL(location.href);next.searchParams.set('lang',locale);history.replaceState(null,'',next);},[locale,mode,t.requestTitle,t.statusTitle,base.brand]);
 useEffect(()=>{if(result) resultRef.current?.focus();},[result]);
 const errors: Record<string,string> = {PRIVATE_EMAIL_BLOCKED:t.private, INVALID_INSTITUTION:t.invalidInstitution, REQUEST_NOT_ACCEPTED:t.conflict, STATUS_UNAVAILABLE:t.denied, SERVICE_UNAVAILABLE:t.unavailable, TRY_LATER:t.busy, INVALID_REQUEST:t.invalidInput, UNCERTAIN:t.uncertain, MISMATCH:t.mismatch, CHOOSE:t.choose};
 async function submit(event:FormEvent<HTMLFormElement>) {
  event.preventDefault(); if(sending.current) return; const form=event.currentTarget;const fields=new FormData(form);
  setError(''); setResult(null);
  const password=String(fields.get('password')||'');
  if(mode==='request' && password!==fields.get('confirm')) {setError('MISMATCH');return;}
  if(mode==='request' && !selection) {setError('CHOOSE');return;}
  const payload={email:String(fields.get('email')||''),password,...(mode==='request'?{institution_id:selection,name:String(fields.get('name')||'')}:{})};
  sending.current=true;setBusy(true);const controller=new AbortController();sendAbort.current=controller;
  const timer=setTimeout(()=>controller.abort(),15000);
  try {
   const data=requestStatus(await accessFetch(mode==='request'?'requests':'status',controller.signal,payload));
   if(sendAbort.current!==controller) return;
   form.reset();setResult(data);
   if(mode==='request') {history.replaceState(null,'',url('/account/status'));setMode('status');}
  } catch(cause) {if(sendAbort.current===controller) setError(cause instanceof AccessError ? cause.code : 'SERVICE_UNAVAILABLE');}
  finally {clearTimeout(timer);form.querySelectorAll<HTMLInputElement>('input[type=password]').forEach(input=>{input.value='';});sending.current=false;setBusy(false);}
 }
 const statusLabel = result ? {pending:t.pendingLabel,approved:t.approved,rejected:t.rejected,deactivated:t.deactivated}[result.status] : '';
 const stamp = (value:string) => new Intl.DateTimeFormat(locale === 'en' ? 'en-GB' : locale,{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Belgrade'}).format(new Date(value));
 return <><a className="skip" href="#main">{base.skip}</a><div className="site"><header><a className="brand" href={url('/')}><span className="brand-mark" aria-hidden="true">OD<span/></span>{base.brand}</a><nav className="languages" aria-label={base.language}>{locales.map(lang=><button key={lang} type="button" lang={lang} aria-pressed={locale===lang} onClick={()=>setLocale(lang)}>{languageNames[lang]}</button>)}</nav></header>
 <main id="main" className="access-main"><nav className="access-nav" aria-label={t.eyebrow}><a href={url('/')}>{t.back}</a><a href={url(mode==='request'?'/account/status':'/account/request')}>{mode==='request'?t.statusTitle:t.newRequest}</a></nav><div className="access-layout"><aside className="access-intro"><p className="eyebrow">{t.eyebrow}</p><h1>{t.title}</h1><p className="lead">{t.intro}</p><p className="access-notice">{t.noEmail}</p><ol className="access-process"><li><span>01</span>{t.requestTitle}</li><li><span>02</span>{t.pendingLabel}</li><li><span>03</span>{t.approved}</li></ol><p className="scope">{base.draft}</p></aside>
 <section className="access-card" aria-labelledby="access-heading"><p className="eyebrow">{mode==='request'?'01 / 03':'02 / 03'}</p><h2 id="access-heading">{mode==='request'?t.requestTitle:t.statusTitle}</h2>
 {result && <section className="access-result" data-status={result.status} aria-live="polite"><h3 ref={resultRef} tabIndex={-1}>{result.status==='pending'?t.pending:statusLabel}</h3><span className="status-badge">{statusLabel}</span>{result.status==='pending'&&<p>{t.pendingHint}</p>}{result.domain_review&&<p>{result.domain_review==='matched'?t.matched:t.unconfirmed}</p>}<dl>{result.institution_name&&<><dt>{t.institution}</dt><dd>{result.institution_name}</dd></>}{result.email&&<><dt>{t.email}</dt><dd>{result.email}</dd></>}<dt>{t.requested}</dt><dd>{stamp(result.requested_at)}</dd>{result.reviewed_at&&<><dt>{t.reviewed}</dt><dd>{stamp(result.reviewed_at)}</dd></>}{result.decision_reason&&<><dt>{t.reason}</dt><dd>{result.decision_reason}</dd></>}</dl><p className="scope">{t.next}</p>{result.status==='approved'&&<a className="access-link" href={url('/sign-in')}>{authMessages[locale].login}</a>}</section>}
 {mode==='request'&&<><p className="synthetic-note">{t.synthetic}</p><form className="institution-search" onSubmit={e=>{e.preventDefault();void search(searchRef.current?.value||'');}}><label htmlFor="institution-search">{t.find}</label><div><input id="institution-search" ref={searchRef} type="search" maxLength={100} placeholder={t.searchPlaceholder}/><button type="submit" disabled={listState==='loading'}>{t.search}</button></div></form><p className="list-info" role="status">{listState==='loading'?base.loading:listState==='error'?t.listFailed:more?t.more:items.length===0?t.empty:''}</p></>}
 <form className="access-form" onSubmit={e=>void submit(e)} aria-busy={busy}><p className="scope">{mode==='status'?t.statusHint:t.required}</p>
 {mode==='request'&&<><label htmlFor="institution">{t.institution}</label><select id="institution" name="institution_id" required disabled={listState!=='ready'||busy} value={selection} onChange={e=>setSelection(e.target.value)}><option value="">{t.select}</option>{items.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><label htmlFor="name">{t.name}</label><input id="name" name="name" required maxLength={150} autoComplete="name" disabled={busy}/></>}
 <label htmlFor="email">{t.email}</label><input id="email" name="email" type="email" required maxLength={254} autoComplete="username" disabled={busy}/>
 <label htmlFor="password">{t.password}</label><input id="password" name="password" type="password" required minLength={15} maxLength={128} autoComplete={mode==='request'?'new-password':'current-password'} aria-describedby="password-hint" disabled={busy}/><p id="password-hint" className="field-hint">{t.passwordHint}</p>
 {mode==='request'&&<><label htmlFor="confirm">{t.confirm}</label><input id="confirm" name="confirm" type="password" required minLength={15} maxLength={128} autoComplete="new-password" disabled={busy}/></>}
 {error&&<p role="alert" className="access-error">{errors[error]||t.unavailable}</p>}
 <button type="submit" className="refresh" disabled={busy||(mode==='request'&&(listState!=='ready'||!selection))}>{busy?(mode==='request'?t.submitting:t.checking):mode==='request'?t.submit:t.viewStatus}<span aria-hidden="true">↗</span></button></form>
 </section></div></main><footer><span>{base.footer}</span><span>{base.draft}</span></footer></div></>;
}
