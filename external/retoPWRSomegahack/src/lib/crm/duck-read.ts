import { gatewayBaseUrl, postGatewayDbRead } from '@/lib/duckclaw-gateway';
import { crmDuckDbPath, crmTenantId, crmVaultUserId } from '@/lib/crm/config';
import type { Ticket, TicketsFilter } from '@/types';
import { rowToTicket } from '@/lib/crm/map-rows';

export async function readTicketsFromDuckDb(
  idSecretaria: string,
  filters?: TicketsFilter
): Promise<{ ok: true; tickets: Ticket[] } | { ok: false; detail: string }> {
  const base = gatewayBaseUrl();
  const dbPath = crmDuckDbPath();
  if (!base || !dbPath) {
    return { ok: false, detail: 'Config CRM incompleta' };
  }
  const userId = crmVaultUserId();
  const tenantId = crmTenantId();

  let sql = `
    SELECT id_ticket, tipo_solicitud, id_secretaria, fecha_creacion, fecha_limite, estado,
           contenido_raw, resumen_ia, respuesta_sugerida, canal_origen, nombre_ciudadano
    FROM pqrsd_crm.tickets
    WHERE id_secretaria = ?
  `.trim();
  const params: unknown[] = [idSecretaria];

  if (filters?.estado && filters.estado !== 'Todos') {
    sql += ' AND estado = ?';
    params.push(filters.estado);
  }
  if (filters?.tipoSolicitud && filters.tipoSolicitud !== 'Todos') {
    sql += ' AND tipo_solicitud = ?';
    params.push(filters.tipoSolicitud);
  }
  if (filters?.searchQuery?.trim()) {
    const q = `%${filters.searchQuery.trim().toLowerCase()}%`;
    sql += ' AND (LOWER(contenido_raw) LIKE ? OR LOWER(nombre_ciudadano) LIKE ?)';
    params.push(q, q);
  }

  sql += ' ORDER BY fecha_creacion DESC';

  const r = await postGatewayDbRead(base, {
    query: sql,
    params,
    user_id: userId,
    db_path: dbPath,
    tenant_id: tenantId,
  });
  if (!r.ok) {
    return { ok: false, detail: r.detail ?? 'Lectura CRM falló' };
  }
  const tickets = r.rows.map((row) => rowToTicket(row));
  return { ok: true, tickets };
}

export async function readTicketByIdFromDuckDb(
  idTicket: string,
  idSecretaria: string
): Promise<{ ok: true; ticket: Ticket } | { ok: false; detail: string; code?: string }> {
  const base = gatewayBaseUrl();
  const dbPath = crmDuckDbPath();
  if (!base || !dbPath) {
    return { ok: false, detail: 'Config CRM incompleta' };
  }
  const userId = crmVaultUserId();
  const tenantId = crmTenantId();

  const r = await postGatewayDbRead(base, {
    query: `
      SELECT id_ticket, tipo_solicitud, id_secretaria, fecha_creacion, fecha_limite, estado,
             contenido_raw, resumen_ia, respuesta_sugerida, canal_origen, nombre_ciudadano
      FROM pqrsd_crm.tickets
      WHERE id_ticket = ? AND id_secretaria = ?
      LIMIT 1
    `.trim(),
    params: [idTicket, idSecretaria],
    user_id: userId,
    db_path: dbPath,
    tenant_id: tenantId,
  });
  if (!r.ok) {
    return { ok: false, detail: r.detail ?? 'Lectura CRM falló' };
  }
  const row = r.rows[0];
  if (!row) {
    return { ok: false, detail: 'NOT_FOUND', code: 'NOT_FOUND' };
  }
  return { ok: true, ticket: rowToTicket(row) };
}
