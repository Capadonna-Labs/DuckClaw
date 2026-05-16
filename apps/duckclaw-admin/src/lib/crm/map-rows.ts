import type { CanalOrigen, Ticket, TicketEstado, TipoSolicitud } from '@/types';

export function rowToTicket(r: Record<string, unknown>): Ticket {
  const idTicket = String(r.id_ticket ?? '');
  return {
    idTicket,
    tipoSolicitud: String(r.tipo_solicitud ?? 'Peticion') as TipoSolicitud,
    idSecretaria: String(r.id_secretaria ?? ''),
    fechaCreacion: toIso(r.fecha_creacion),
    fechaLimite: toIso(r.fecha_limite),
    estado: String(r.estado ?? 'Pendiente') as TicketEstado,
    contenidoRaw: String(r.contenido_raw ?? ''),
    resumenIa: r.resumen_ia == null ? null : String(r.resumen_ia),
    respuestaSugerida: r.respuesta_sugerida == null ? null : String(r.respuesta_sugerida),
    canalOrigen: String(r.canal_origen ?? 'Web') as CanalOrigen,
    nombreCiudadano: String(r.nombre_ciudadano ?? ''),
    numeroRadicado: String(r.numero_radicado ?? idTicket),
    emailCiudadano: r.email_ciudadano == null ? null : String(r.email_ciudadano),
  };
}

function toIso(v: unknown): string {
  if (v instanceof Date) return v.toISOString();
  if (typeof v === 'string') return v;
  return String(v ?? '');
}
