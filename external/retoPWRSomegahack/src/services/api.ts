export const API_CONFIG = {
  BASE_URL: process.env.NEXT_PUBLIC_API_URL ?? 'mock',
  USE_MOCK: process.env.NEXT_PUBLIC_API_URL === undefined || 
            process.env.NEXT_PUBLIC_API_URL === 'mock',
  TIMEOUT_MS: 10000,
};

/** 
 * MENSAJE DE INTEGRACIÓN (Handover):
 * Cuando el backend DuckDB esté disponible para el Distrito de Medellín, 
 * realice los siguientes cambios:
 * 1. Configure NEXT_PUBLIC_API_URL en su archivo .env.local con la URL base del servidor REST.
 * 2. Asegúrese de que el servidor exponga los siguientes endpoints compatibles:
 * 
 *   GET  /api/tickets?idSecretaria={id}&estado={estado}&tipoSolicitud={tipo}&search={query}
 *        Retorna: { data: Ticket[], total: number, timestamp: string }
 * 
 *   GET  /api/tickets/{id}?idSecretariaUsuario={id}
 *        Retorna: { data: Ticket, total: 1, timestamp: string }
 *        Debe validar que el ticket pertenezca a la secretaría del funcionario.
 * 
 *   PUT  /api/tickets/{id}/responder
 *        Body: { respuestaFinal: string, idSecretariaUsuario: string }
 *        Retorna: { data: { success: boolean }, timestamp: string }
 * 
 *   GET  /api/secretarias
 *        Retorna: { data: Secretaria[], total: number, timestamp: string }
 */
