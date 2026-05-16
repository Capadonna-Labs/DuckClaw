/**
 * Cliente mínimo para proxies Next.js → DuckClaw API Gateway (worker PQRSD-Assistant, tenant PQRS).
 */

export type GatewayChatPayload = Record<string, unknown>;

export function gatewayBaseUrl(): string | null {
  const raw =
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    '';
  if (!raw) return null;
  return raw.replace(/\/$/, '');
}

/** user_id efectivo hacia el gateway (whitelist); override en dev vía env. */
export function crmGatewayUserId(duckclawUserId: string): string {
  return (
    process.env.DUCKCLAW_GATEWAY_USER_ID_OVERRIDE?.trim() ||
    (duckclawUserId || '').trim() ||
    'crm-anonymous'
  );
}

export function responseTextFromGatewayPayload(payload: GatewayChatPayload): string {
  const r = payload.response;
  const t = payload.text;
  if (typeof r === 'string') return r;
  if (typeof t === 'string') return t;
  return '';
}

export type GatewayDbWritePayload = {
  query: string;
  params?: unknown[];
  user_id: string;
  db_path: string;
  tenant_id?: string;
};

export type GatewayDbReadPayload = GatewayDbWritePayload;

/** Encola escritura DuckDB vía API Gateway (db-writer). */
export async function postGatewayDbWrite(
  base: string,
  body: GatewayDbWritePayload
): Promise<{ ok: boolean; status: number; taskId?: string; detail?: string }> {
  try {
    const res = await fetch(`${base}/api/v1/db/write`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: body.query,
        params: body.params ?? [],
        user_id: body.user_id,
        db_path: body.db_path,
        tenant_id: body.tenant_id ?? 'PQRS',
      }),
      cache: 'no-store',
    });
    let taskId: string | undefined;
    let detail: string | undefined;
    try {
      const j = (await res.json()) as { task_id?: string; detail?: string };
      taskId = j.task_id;
      detail = j.detail;
    } catch {
      detail = await res.text();
    }
    return { ok: res.ok, status: res.status, taskId, detail };
  } catch (err) {
    return {
      ok: false,
      status: 503,
      detail: `Error de conexión al Gateway (${base}): ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/** SELECT en solo lectura vía API Gateway (Python duckdb). */
export async function postGatewayDbRead(
  base: string,
  body: GatewayDbReadPayload
): Promise<{ ok: boolean; status: number; rows: Record<string, unknown>[]; detail?: string }> {
  try {
    const res = await fetch(`${base}/api/v1/db/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: body.query,
        params: body.params ?? [],
        user_id: body.user_id,
        db_path: body.db_path,
        tenant_id: body.tenant_id ?? 'PQRS',
      }),
      cache: 'no-store',
    });
    const raw = await res.text();
    try {
      const j = JSON.parse(raw) as { rows?: Record<string, unknown>[]; detail?: string };
      if (res.ok && Array.isArray(j.rows)) {
        return { ok: true, status: res.status, rows: j.rows };
      }
      return {
        ok: false,
        status: res.status,
        rows: [],
        detail: j.detail ?? raw,
      };
    } catch {
      return { ok: false, status: res.status, rows: [], detail: raw };
    }
  } catch (err) {
    return {
      ok: false,
      status: 503,
      rows: [],
      detail: `Error de conexión al Gateway (${base}): ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

export async function postPqrsAssistantChat(
  base: string,
  chatRequest: Record<string, unknown>
): Promise<{ ok: boolean; status: number; rawText: string; payload: GatewayChatPayload }> {
  const url = `${base}/api/v1/agent/${encodeURIComponent('PQRSD-Assistant')}/chat`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-Id': 'PQRS' },
    body: JSON.stringify(chatRequest),
    cache: 'no-store',
  });
  const rawText = await res.text();
  let payload: GatewayChatPayload = {};
  try {
    payload = rawText ? (JSON.parse(rawText) as GatewayChatPayload) : {};
  } catch {
    payload = {};
  }
  return { ok: res.ok, status: res.status, rawText, payload };
}
