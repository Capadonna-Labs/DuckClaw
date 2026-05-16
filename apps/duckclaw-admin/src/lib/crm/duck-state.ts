import { gatewayBaseUrl, postGatewayDbWrite } from '@/lib/duckclaw-gateway';
import { crmDuckDbPath, crmTenantId, crmVaultUserId } from '@/lib/crm/config';
import type { TicketEstado } from '@/types';

export async function updateTicketEstadoInDuckDb(
  idTicket: string,
  idSecretaria: string,
  nuevoEstado: TicketEstado
): Promise<{ ok: true } | { ok: false; detail: string }> {
  const base = gatewayBaseUrl();
  const dbPath = crmDuckDbPath();
  if (!base || !dbPath) {
    return { ok: false, detail: 'Config CRM incompleta' };
  }
  const userId = crmVaultUserId();
  const tenantId = crmTenantId();

  const w = await postGatewayDbWrite(base, {
    query: `
      UPDATE pqrsd_crm.tickets
      SET estado = ?, fecha_actualizacion = CURRENT_TIMESTAMP
      WHERE id_ticket = ? AND id_secretaria = ?
    `.trim(),
    params: [nuevoEstado, idTicket, idSecretaria],
    user_id: userId,
    db_path: dbPath,
    tenant_id: tenantId,
  });
  if (!w.ok) {
    return { ok: false, detail: w.detail ?? `Gateway (${w.status})` };
  }
  return { ok: true };
}
