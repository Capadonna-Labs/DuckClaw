import type { Ticket } from '@/types';
import { TICKETS_MOCK } from '@/services/mockData';
import { postGatewayDbRead, postGatewayDbWrite, gatewayBaseUrl } from '@/lib/duckclaw-gateway';
import {
  crmAutoBootstrap,
  crmDuckDbPath,
  crmTenantId,
  crmVaultUserId,
} from '@/lib/crm/config';
import { crmUsesDuckDb } from '@/lib/crm/crm-mode';
import { PQRS_CRM_DDL_STATEMENTS } from '@/lib/crm/schema-ddl';

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function pollUntilTableReadable(
  base: string,
  dbPath: string,
  userId: string,
  tenantId: string,
  maxAttempts = 40
): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i++) {
    const r = await postGatewayDbRead(base, {
      query: 'SELECT 1 AS ok FROM pqrsd_crm.tickets LIMIT 1',
      params: [],
      user_id: userId,
      db_path: dbPath,
      tenant_id: tenantId,
    });
    if (r.ok) return true;
    await sleep(150);
  }
  return false;
}

function ticketInsertParams(t: Ticket): unknown[] {
  return [
    t.idTicket,
    t.numeroRadicado,
    t.tipoSolicitud,
    t.idSecretaria,
    t.fechaCreacion,
    t.fechaLimite,
    t.estado,
    t.contenidoRaw,
    t.resumenIa,
    t.respuestaSugerida,
    t.canalOrigen,
    t.nombreCiudadano,
    t.emailCiudadano ?? null,
    t.asunto ?? 'Solicitud PQRSD',
  ];
}

/**
 * Asegura esquema/tablas (vía Gateway) y opcionalmente seed desde mock si tabla vacía.
 * Pensado para dev con CRM_AUTO_BOOTSTRAP=true; en prod aplicar DDL al archivo DuckDB.
 */
export async function ensureCrmSchemaAndSeed(): Promise<{ ok: boolean; detail?: string }> {
  const dbPath = crmDuckDbPath();
  const base = gatewayBaseUrl();
  if (!dbPath || !base) {
    return { ok: false, detail: 'DUCKCLAW_PQRSD_ASSISTANT_DB_PATH (o CRM_DUCKDB_PATH) o gateway URL no configurados' };
  }
  const userId = crmVaultUserId();
  const tenantId = crmTenantId();

  for (const q of PQRS_CRM_DDL_STATEMENTS) {
    const w = await postGatewayDbWrite(base, {
      query: q,
      params: [],
      user_id: userId,
      db_path: dbPath,
      tenant_id: tenantId,
    });
    if (!w.ok) {
      return { ok: false, detail: w.detail ?? `DDL falló (${w.status})` };
    }
  }

  const visible = await pollUntilTableReadable(base, dbPath, userId, tenantId);
  if (!visible) {
    return { ok: false, detail: 'Timeout esperando que db-writer aplique el DDL' };
  }

  if (!crmAutoBootstrap()) {
    return { ok: true };
  }

  const cnt = await postGatewayDbRead(base, {
    query: 'SELECT COUNT(*) AS c FROM pqrsd_crm.tickets',
    params: [],
    user_id: userId,
    db_path: dbPath,
    tenant_id: tenantId,
  });
  const n = Number(cnt.rows[0]?.c ?? 0);
  if (n > 0) {
    return { ok: true };
  }

  for (const t of TICKETS_MOCK) {
    const p = ticketInsertParams(t);
    const w = await postGatewayDbWrite(base, {
      query: `INSERT INTO pqrsd_crm.tickets (
        id_ticket, numero_radicado, tipo_solicitud, id_secretaria, fecha_creacion, fecha_limite, estado,
        contenido_raw, resumen_ia, respuesta_sugerida, canal_origen, nombre_ciudadano,
        email_ciudadano, asunto, fecha_actualizacion
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
      params: p,
      user_id: userId,
      db_path: dbPath,
      tenant_id: tenantId,
    });
    if (!w.ok) {
      return { ok: false, detail: w.detail ?? `Seed falló en ${t.idTicket}` };
    }
  }

  for (let i = 0; i < 80; i++) {
    const c2 = await postGatewayDbRead(base, {
      query: 'SELECT COUNT(*) AS c FROM pqrsd_crm.tickets',
      params: [],
      user_id: userId,
      db_path: dbPath,
      tenant_id: tenantId,
    });
    if (Number(c2.rows[0]?.c ?? 0) >= 1) {
      return { ok: true };
    }
    await sleep(100);
  }
  return { ok: false, detail: 'Timeout esperando seed en pqrsd_crm.tickets' };
}

let bootstrapAttempted = false;

/** Si CRM_AUTO_BOOTSTRAP, aplica DDL/seed una vez por proceso (dev). */
export async function ensureCrmReady(): Promise<{ ok: boolean; detail?: string }> {
  if (!crmUsesDuckDb()) return { ok: true };
  if (!crmAutoBootstrap()) return { ok: true };
  if (bootstrapAttempted) return { ok: true };
  bootstrapAttempted = true;
  return ensureCrmSchemaAndSeed();
}
