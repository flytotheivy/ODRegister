export type Profile={id:string;name:string;role:'institution_user'|'ADMIN_MPALSG'|'ADMIN_ITE';institution_id:string|null;csrf_token:string};
export type ReviewItem={id:string;name:string;email:string;institution_id:string;institution_name:string;status:'pending'|'approved'|'rejected'|'deactivated';requested_at:string;reviewed_at:string|null;reviewer_name:string|null;approval_reference:string|null;decision_reason:string|null;domain_review:'matched'|'unconfirmed';institution_active:boolean;domain_policy:{domain:string;verified_at:string;evidence_reference:string}|null};
export type AccountList={items:ReviewItem[];has_more:boolean;counts:Record<'pending'|'approved'|'rejected'|'deactivated',number>};
export class AuthError extends Error {code:string;constructor(code:string){super('Authentication request failed');this.code=code;}}
export async function authFetch(path:string,payload?:object,csrf?:string,signal?:AbortSignal):Promise<unknown>{
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);const stop=()=>controller.abort();signal?.addEventListener('abort',stop,{once:true});if(signal?.aborted)controller.abort();
 try{
  const response=await fetch('/api/'+path,{method:payload?'POST':'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(payload?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{})},...(payload?{body:JSON.stringify(payload)}:{})});
  const body=await response.json();if(!response.ok)throw new AuthError(body?.error?.code||'SERVICE_UNAVAILABLE');return body;
 }catch(error){if(error instanceof AuthError)throw error;throw new AuthError('SERVICE_UNAVAILABLE');}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',stop);}
}
export function profile(value:unknown):Profile{
 const v=value as Profile;if(!v||typeof v.id!=='string'||typeof v.name!=='string'||!['institution_user','ADMIN_MPALSG','ADMIN_ITE'].includes(v.role)||!/^([0-9a-f]{64})$/.test(v.csrf_token)||(v.institution_id!==null&&typeof v.institution_id!=='string'))throw new AuthError('SERVICE_UNAVAILABLE');return v;
}
export function accountList(value:unknown):AccountList{
 const v=value as AccountList;if(!v||!Array.isArray(v.items)||typeof v.has_more!=='boolean'||!v.counts||!['pending','approved','rejected','deactivated'].every(k=>Number.isInteger(v.counts[k as keyof typeof v.counts])&&v.counts[k as keyof typeof v.counts]>=0)||!v.items.every(x=>!!x&&typeof x==='object'&&typeof x.id==='string'&&typeof x.email==='string'&&typeof x.name==='string'&&typeof x.institution_name==='string'&&['pending','approved','rejected','deactivated'].includes(x.status)&&['matched','unconfirmed'].includes(x.domain_review)))throw new AuthError('SERVICE_UNAVAILABLE');return v;
}
