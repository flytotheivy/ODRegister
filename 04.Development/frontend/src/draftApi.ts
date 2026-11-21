import {AuthError} from './authApi.ts';
import {cyclePage,themeCatalogue,type Cycle,type Theme} from './cyclesApi.ts';
export type DraftItem={id:string|null;title:string|null;description:string|null;responsible_department:string|null;planned_quarter:number|null;theme_id:string|null;personal_data_confirmation?:boolean;position?:number};
export type DraftPlan={id:string;status:'draft'|'submitted';revision:number;created_at:string;updated_at:string;first_submitted_at:string|null;items:DraftItem[]};
export type DraftDocument={cycle:Cycle;institution:{id:string;name:string};themes:Theme[];plan:DraftPlan|null};
export type AnnualRow={cycle:Cycle;institution_name:string;plan:(Omit<DraftPlan,'items'|'created_at'>&{item_count:number})|null};
export type AnnualPage={items:AnnualRow[];next_cursor:number|null};
const uuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
const date=(v:unknown)=>typeof v==='string'&&Number.isFinite(Date.parse(v));
function checkCycle(c:Cycle){cyclePage({items:[c],next_cursor:null,active_register_count:0});}
function planHeader(p:DraftPlan|NonNullable<AnnualRow['plan']>){return uuid(p.id)&&['draft','submitted'].includes(p.status)&&Number.isSafeInteger(p.revision)&&p.revision>0&&date(p.updated_at)&&(p.status==='submitted'?date(p.first_submitted_at):p.first_submitted_at===null);}
export function draftDocument(v:unknown):DraftDocument{
 const d=v as DraftDocument;if(!d||!d.institution||!uuid(d.institution.id)||typeof d.institution.name!=='string')throw new AuthError('SERVICE_UNAVAILABLE');checkCycle(d.cycle);themeCatalogue({items:d.themes});
 if(d.plan!==null){const p=d.plan;if(!p||!planHeader(p)||!date(p.created_at)||!Array.isArray(p.items)||!p.items.every(i=>!!i&&uuid(i.id)&&Number.isInteger(i.position)&&(i.position??0)>0&&typeof i.personal_data_confirmation==='boolean'&&['title','description','responsible_department'].every(k=>i[k as keyof DraftItem]===null||typeof i[k as keyof DraftItem]==='string')&&(i.theme_id===null||uuid(i.theme_id))&&(i.planned_quarter===null||Number.isInteger(i.planned_quarter)&&i.planned_quarter>=1&&i.planned_quarter<=4)))throw new AuthError('SERVICE_UNAVAILABLE');}
 return d;
}
export function annualPage(v:unknown):AnnualPage{const d=v as AnnualPage;if(!d||!Array.isArray(d.items)||(d.next_cursor!==null&&!Number.isInteger(d.next_cursor)))throw new AuthError('SERVICE_UNAVAILABLE');for(const row of d.items){checkCycle(row.cycle);if(typeof row.institution_name!=='string'||row.plan!==null&&(!row.plan||!planHeader(row.plan)||!Number.isInteger(row.plan.item_count)||row.plan.item_count<0))throw new AuthError('SERVICE_UNAVAILABLE');}return d;}
export function draftPayload(items:DraftItem[],revision:number){return {expected_revision:revision,items:items.map(i=>({id:i.id,title:i.title,description:i.description,responsible_department:i.responsible_department,planned_quarter:i.planned_quarter,theme_id:i.theme_id,personal_data_confirmation:i.personal_data_confirmation===true}))};}
export function emptyItem():DraftItem{return {id:null,title:null,description:null,responsible_department:null,planned_quarter:null,theme_id:null,personal_data_confirmation:false};}
