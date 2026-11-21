export type Health = {service: 'layer1'; status: 'ready'; checks: {api: 'ok'; database: 'ok'}; request_id: string};
export type HealthResult = {kind: 'ready'; data: Health} | {kind: 'unavailable' | 'invalid' | 'timeout'};
export function isHealth(value: unknown): value is Health {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<Health>;
  if (Object.keys(value).sort().join(',') !== 'checks,request_id,service,status') return false;
  if (!v.checks || Object.keys(v.checks).sort().join(',') !== 'api,database') return false;
  return v.service === 'layer1' && v.status === 'ready' && v.checks?.api === 'ok' && v.checks?.database === 'ok'
    && typeof v.request_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(v.request_id);
}
export async function fetchHealth(signal: AbortSignal): Promise<HealthResult> {
  try {
    const response = await fetch('/api/health', {signal, cache: 'no-store', headers: {Accept: 'application/json'}});
    if (!response.ok) return {kind: 'unavailable'};
    let body: unknown;
    try { body = await response.json(); } catch { return {kind: signal.aborted ? 'timeout' : 'invalid'}; }
    return isHealth(body) ? {kind: 'ready', data: body} : {kind: 'invalid'};
  } catch {
    return {kind: signal.aborted ? 'timeout' : 'unavailable'};
  }
}
