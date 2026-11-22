import {useId} from 'react';
export type ChartRow={label:string;value:number;note?:string};
export function BarChart({title,rows,tableLabel,max}:{title:string;rows:ChartRow[];tableLabel:string;max?:number}){
 const id=useId(),limit=max??Math.max(0,...rows.map(r=>r.value));
 return <figure className="data-chart" aria-labelledby={id}><figcaption id={id}>{title}</figcaption><ol className="bar-chart">{rows.map((row,i)=><li key={i}><div className="bar-caption"><span>{row.label}</span><strong>{row.value.toLocaleString()}<small>{row.note}</small></strong></div><div className="bar-track" aria-hidden="true"><span style={{width:(limit>0?Math.min(100,Math.max(0,row.value/limit*100)):0)+'%'}}/></div></li>)}</ol><details className="chart-table"><summary>{tableLabel}</summary><table><caption>{title}</caption><thead><tr><th scope="col">{title}</th><th scope="col">#</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><th scope="row">{r.label}</th><td>{r.value}{r.note?' · '+r.note:''}</td></tr>)}</tbody></table></details></figure>;
}
export function StatusChart({title,rows,tableLabel}:{title:string;rows:ChartRow[];tableLabel:string}){
 const total=rows.reduce((sum,r)=>sum+r.value,0);let offset=0;
 return <section className="status-chart"><div className="donut" aria-hidden="true"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="48" fill="none" stroke="var(--line)" strokeWidth="12"/>{rows.map((r,i)=>{const size=total?r.value/total*100:0,start=offset;offset+=size;return <circle key={i} cx="60" cy="60" r="48" pathLength="100" fill="none" className={'segment segment-'+i} strokeWidth="12" strokeDasharray={`${size} ${100-size}`} strokeDashoffset={-start} transform="rotate(-90 60 60)"/>;})}</svg><span>{total.toLocaleString()}</span></div><BarChart title={title} rows={rows} tableLabel={tableLabel} max={total}/></section>;
}
