/**
 * Mapea una fila DuckDB pqrsd_crm.tickets (snake_case) a un objeto Ticket (camelCase).
 */

interface TicketRow {
  id_ticket: string;
  numero_radicado: string;
  id_secretaria: string;
  nombre_ciudadano: string;
  documento_ciudadano?: string | null;
  email_ciudadano: string | null;
  telefono_ciudadano?: string | null;
  tipo_solicitud: string;
  asunto: string;
  contenido_raw: string;
  resumen_ia: string | null;
  respuesta_sugerida: string | null;
  estado: string;
  canal_origen: string;
  fecha_creacion: string | Date;
  fecha_limite: string | Date;
  fecha_actualizacion?: string | Date;
}

export function mapRowToTicket(row: unknown) {
  const r = row as TicketRow;
  return {
    idTicket: r.id_ticket,
    numeroRadicado: r.numero_radicado,
    idSecretaria: r.id_secretaria,
    nombreCiudadano: r.nombre_ciudadano,
    documentoCiudadano: r.documento_ciudadano,
    emailCiudadano: r.email_ciudadano,
    telefonoCiudadano: r.telefono_ciudadano,
    tipoSolicitud: r.tipo_solicitud,
    asunto: r.asunto,
    contenidoRaw: r.contenido_raw,
    resumenIa: r.resumen_ia,
    respuestaSugerida: r.respuesta_sugerida,
    estado: r.estado,
    canalOrigen: r.canal_origen,
    fechaCreacion: typeof r.fecha_creacion === 'object' ? (r.fecha_creacion as Date).toISOString() : r.fecha_creacion,
    fechaLimite: typeof r.fecha_limite === 'object' ? (r.fecha_limite as Date).toISOString() : r.fecha_limite,
  };
}
