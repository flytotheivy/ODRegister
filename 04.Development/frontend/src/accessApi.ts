export type Institution = {id: string; name: string; synthetic: boolean};
export type RequestStatus = {institution_name?: string; email?: string; status: 'pending' | 'approved' | 'rejected' | 'deactivated'; requested_at: string; reviewed_at?: string | null; decision_reason?: string | null; domain_review?: 'matched' | 'unconfirmed'; request_id: string};
export class AccessError extends Error {code: string; constructor(code: string) {super('Access request failed'); this.code = code;}}
export async function accessFetch(path: string, signal: AbortSignal, payload?: object): Promise<unknown> {
  let response: Response;
  try {response = await fetch('/api/access/' + path, {method: payload ? 'POST' : 'GET', signal, cache: 'no-store', credentials: 'omit', headers: {Accept: 'application/json', ...(payload ? {'Content-Type': 'application/json'} : {})}, ...(payload ? {body: JSON.stringify(payload)} : {})});}
  catch {throw new AccessError('UNCERTAIN');}
  let data: unknown;
  try {data = await response.json();} catch {throw new AccessError('UNCERTAIN');}
  if (!response.ok) {
    const error = data as {error?: {code?: string}};
    throw new AccessError(error?.error?.code || 'SERVICE_UNAVAILABLE');
  }
  return data;
}
export function institutionList(value: unknown): {items: Institution[]; has_more: boolean} {
  const v = value as {items?: unknown[]; has_more?: boolean};
  if (!v || !Array.isArray(v.items) || typeof v.has_more !== 'boolean' || !v.items.every(row => !!row && typeof row === 'object' && typeof (row as Institution).id === 'string' && typeof (row as Institution).name === 'string' && typeof (row as Institution).synthetic === 'boolean')) throw new AccessError('SERVICE_UNAVAILABLE');
  return v as {items: Institution[]; has_more: boolean};
}
export function requestStatus(value: unknown): RequestStatus {
  const v = value as RequestStatus;
  if (!v || (v.email != null && typeof v.email !== 'string') || (v.institution_name != null && typeof v.institution_name !== 'string') || !['pending', 'approved', 'rejected', 'deactivated'].includes(v.status) || typeof v.requested_at !== 'string' || !Number.isFinite(Date.parse(v.requested_at)) || typeof v.request_id !== 'string' || (v.reviewed_at != null && (typeof v.reviewed_at !== 'string' || !Number.isFinite(Date.parse(v.reviewed_at)))) || (v.decision_reason != null && typeof v.decision_reason !== 'string') || (v.domain_review != null && !['matched', 'unconfirmed'].includes(v.domain_review))) throw new AccessError('UNCERTAIN');
  return v;
}
