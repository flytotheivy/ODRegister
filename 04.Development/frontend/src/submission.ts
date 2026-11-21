import type {DraftItem} from './draftApi.ts';
export type SubmissionIssue={index:number;field:'items'|'title'|'theme_id'|'personal_data_confirmation'};
export function submissionIssues(items:DraftItem[],activeThemeIds:string[]):SubmissionIssue[]{
 if(items.length===0)return [{index:0,field:'items'}];
 return items.flatMap((item,index)=>{
  const result:SubmissionIssue[]=[];
  if(!item.title?.trim())result.push({index,field:'title'});
  if(!item.theme_id||!activeThemeIds.includes(item.theme_id))result.push({index,field:'theme_id'});
  if(item.personal_data_confirmation!==true)result.push({index,field:'personal_data_confirmation'});
  return result;
 });
}
export function changedItem(item:DraftItem,field:keyof DraftItem,value:unknown):DraftItem{
 return {...item,[field]:value,...(field!=='personal_data_confirmation'&&item[field]!==value?{personal_data_confirmation:false}:{})};
}
