import type {KeyboardEvent as ReactKeyboardEvent,MouseEventHandler,ReactNode,Ref} from 'react';
/* EDS 대응 공통 표시 부품(표시 전용, 업무 로직 없음) */

/** EDS Breadcrumbs: 마지막 항목은 현재 위치(링크 없음) */
export function Breadcrumbs({items,label,onLink}:{items:Array<[string,string?]>;label:string;onLink?:MouseEventHandler<HTMLAnchorElement>}){
 return <nav className="breadcrumbs" aria-label={label}><ol>{items.map(([text,href],i)=>{const last=i===items.length-1;return <li key={i}>{last||!href?<span aria-current={last?'page':undefined}>{text}</span>:<a href={href} onClick={onLink}>{text}</a>}</li>;})}</ol></nav>;
}

/** 화면 머리: 상위 분류·제목·설명·오른쪽 행동 */
export function PageHeader({eyebrow,title,lead,aside,titleRef}:{eyebrow?:ReactNode;title:ReactNode;lead?:ReactNode;aside?:ReactNode;titleRef?:Ref<HTMLHeadingElement>}){
 return <div className="page-header"><div className="page-header-text">{eyebrow&&<p className="eyebrow">{eyebrow}</p>}<h1 ref={titleRef} tabIndex={titleRef?-1:undefined}>{title}</h1>{lead&&<p className="lead">{lead}</p>}</div>{aside&&<div className="page-header-aside">{aside}</div>}</div>;
}

/** EDS Chip: 상태 표시(글자 병기, 색만으로 구분하지 않음) */
export function Chip({tone='info',children}:{tone?:'info'|'success'|'warning'|'error'|'neutral';children:ReactNode}){
 return <span className={'chip chip-'+tone}>{children}</span>;
}

/** 진행 단계 표시(입력 → 확인 → 완료). current는 1부터 */
export function Stepper({steps,current,label}:{steps:string[];current:number;label:string}){
 return <ol className="stepper" aria-label={label}>{steps.map((s,i)=>{const n=i+1,state=n<current?'done':n===current?'current':'todo';return <li key={i} className={'step-'+state} aria-current={state==='current'?'step':undefined}><span className="stepper-num" aria-hidden="true">{state==='done'?'✓':n}</span><span>{s}</span></li>;})}</ol>;
}

/** EDS Tabs: 같은 화면 안의 세부 보기 전환(←/→/Home/End 키 지원) */
export function Tabs<T extends string>({tabs,active,onChange,label,idPrefix,children}:{tabs:Array<[T,string]>;active:T;onChange:(v:T)=>void;label:string;idPrefix:string;children:ReactNode}){
 const move=(e:ReactKeyboardEvent<HTMLButtonElement>,i:number)=>{const n=tabs.length;const next=e.key==='ArrowRight'?(i+1)%n:e.key==='ArrowLeft'?(i-1+n)%n:e.key==='Home'?0:e.key==='End'?n-1:-1;if(next<0)return;e.preventDefault();onChange(tabs[next][0]);document.getElementById(idPrefix+'-tab-'+tabs[next][0])?.focus();};
 return <div className="tabs"><div className="tab-list" role="tablist" aria-label={label}>{tabs.map(([v,text],i)=><button key={v} type="button" role="tab" id={idPrefix+'-tab-'+v} aria-selected={active===v} aria-controls={idPrefix+'-panel'} tabIndex={active===v?0:-1} onClick={()=>onChange(v)} onKeyDown={e=>move(e,i)}>{text}</button>)}</div><div className="tab-panel" role="tabpanel" id={idPrefix+'-panel'} aria-labelledby={idPrefix+'-tab-'+active} tabIndex={0}>{children}</div></div>;
}
