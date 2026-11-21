import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchHealth, type HealthResult } from './api';
import { dictionaries, locales, resolveLocale, type Locale } from './i18n';
import './style.css';
import Access from './Access';
import PublicPortal from './PublicPortal';
import DraftPortal from './DraftPortal';
import AuthPortal from './AuthPortal';
import InternalPortal from './InternalPortal';
import MonitoringPortal from './MonitoringPortal';
import RegistryPortal from './RegistryPortal';
import {authMessages} from './authMessages';

const languageNames: Record<Locale, string> = {en: 'English', 'sr-Latn': 'Srpski (latinica)', 'sr-Cyrl': 'Српски (ћирилица)'};
export default function App() {
  if(location.pathname === "/admin") return <MonitoringPortal/>;
  if(location.pathname === "/admin/datasets") return <InternalPortal/>;
  if (location.pathname === "/" || location.pathname === "/plans" || location.pathname.startsWith("/plans/")) return <PublicPortal/>;
  if (location.pathname === '/my-plans' || /^\/my-plans\/\d{4}(\/edit)?$/.test(location.pathname)) return <DraftPortal/>;
  if (['/admin/institutions','/admin/settings'].includes(location.pathname)) return <RegistryPortal/>;
  if (['/sign-in','/admin/accounts'].includes(location.pathname)) return <AuthPortal/>;
  return ['/account/request','/account/status'].includes(location.pathname) ? <Access/> : <Foundation/>;
}
function Foundation() {
  const [locale, setLocale] = useState<Locale>(() => resolveLocale(new URLSearchParams(location.search).get('lang')));
  const [result, setResult] = useState<HealthResult | {kind: 'loading'}>({kind: 'loading'});
  const current = useRef<AbortController | null>(null);
  const t = dictionaries[locale];
  const refresh = useCallback(async () => {
    current.current?.abort();
    const controller = new AbortController(); current.current = controller;
    setResult({kind: 'loading'});
    const timer = window.setTimeout(() => controller.abort(), 5000);
    const next = await fetchHealth(controller.signal);
    clearTimeout(timer);
    if (current.current === controller) setResult(next);
  }, []);
  useEffect(() => { void refresh(); return () => { current.current?.abort(); current.current = null; }; }, [refresh]);
  useEffect(() => {
    document.documentElement.lang = locale; document.title = t.brand;
    const url = new URL(location.href); url.searchParams.set('lang', locale); history.replaceState(null, '', url);
  }, [locale, t.brand]);
  const ready = result.kind === 'ready'; const loading = result.kind === 'loading';
  const status = loading ? t.loading : ready ? t.ready : t.unavailable;
  const hint = ready ? t.readyHint : result.kind === 'invalid' ? t.invalidHint : result.kind === 'timeout' ? t.timeoutHint : t.unavailableHint;
  const steps = [[t.accessTitle, t.accessBody], [t.planTitle, t.planBody], [t.publishTitle, t.publishBody]];
  return <>
    <a className="skip" href="#main">{t.skip}</a>
    <div className="site">
      <header>
        <a className="brand" href={`?lang=${locale}`}><span className="brand-mark" aria-hidden="true">OD<span/></span>{t.brand}</a>
        <nav aria-label={t.language} className="languages">{locales.map(lang => <button key={lang} type="button" lang={lang} aria-pressed={locale === lang} onClick={() => setLocale(lang)}>{languageNames[lang]}</button>)}</nav>
      </header>
      <main id="main">
        <div className="context"><span className="tag">{t.preview}</span><span className="context-line"/></div>
        <div className="hero">
          <section className="intro" aria-labelledby="title">
            <p className="eyebrow">{t.eyebrow}</p>
            <h1 id="title">{t.title}</h1>
            <p className="lead">{t.introduction}</p>
            <p className="scope">{t.scope}</p><a className="access-link" href={`/account/request?lang=${locale}`}>{t.accessTitle} ↗</a><a className="access-link secondary" href={`/sign-in?lang=${locale}`}>{authMessages[locale].login}</a>
          </section>
          <section className="connection" aria-labelledby="connection-heading">
            <div className="connection-top"><span className="mini-rule"/><span aria-hidden="true">↗</span></div>
            <h2 id="connection-heading">{t.statusHeading}</h2>
            <p className="panel-intro">{t.statusIntro}</p>
            <div className={`health ${ready ? 'is-ready' : loading ? 'is-loading' : 'is-unavailable'}`} role="status" aria-label={t.statusLabel} aria-live="polite" aria-busy={loading} data-state={result.kind}>
              <span className="health-dot" aria-hidden="true"/><div><strong>{status}</strong>{!loading && <p>{hint}</p>}</div>
            </div>
            <dl className="checks"><div><dt>{t.api}</dt><dd>{ready ? t.ok : t.unknown}</dd></div><div><dt>{t.database}</dt><dd>{ready ? t.ok : t.unknown}</dd></div></dl>
            <button className="refresh" type="button" disabled={loading} onClick={() => void refresh()}>{loading ? t.loading : t.refresh}<span aria-hidden="true">↗</span></button>
          </section>
        </div>
        <section className="steps" aria-labelledby="steps-title"><h2 id="steps-title">{t.stepsHeading}</h2><div className="step-grid">{steps.map(([title, body], i) => <article key={i}><span className="step-number">0{i + 1}</span><h3>{title}</h3><p>{body}</p><span className="later">{i===0?<a href={`/account/request?lang=${locale}`}>{t.accessTitle}</a>:t.later}</span></article>)}</div></section>
      </main>
      <footer><span>{t.footer}</span><span>{t.draft}</span></footer>
    </div>
  </>;
}
