/** Mensajes legibles cuando el BFF no alcanza el gateway. */

export function isGatewayUnreachableMessage(message: string): boolean {
  const m = message.toLowerCase();
  if (
    m.includes('timeout') ||
    m.includes('timed out') ||
    m.includes('tardó demasiado') ||
    m.includes('aborted due to timeout')
  ) {
    return false;
  }
  return (
    m.includes('internal server error') ||
    m.includes('fetch failed') ||
    m.includes('econnrefused') ||
    m.includes('failed to fetch') ||
    m.includes('network') ||
    m.includes('no responde') ||
    m.includes('gateway no') ||
    m.includes('503')
  );
}

/** Extrae mensaje legible de respuestas FastAPI (detail string u objeto RFC7807). */
export function parseApiErrorDetail(data: unknown, status = 500): string {
  if (!data || typeof data !== 'object') return `Error ${status}`;
  const root = data as Record<string, unknown>;
  if (typeof root.detail === 'string') return root.detail;
  if (root.detail && typeof root.detail === 'object') {
    const inner = root.detail as Record<string, unknown>;
    if (typeof inner.detail === 'string') return inner.detail;
    if (typeof inner.title === 'string') return inner.title;
  }
  if (typeof root.title === 'string') return root.title;
  return `Error ${status}`;
}

export function friendlyGatewayError(raw: string): string {
  const m = raw.toLowerCase();
  if (
    m.includes('timeout') ||
    m.includes('timed out') ||
    m.includes('aborted due to timeout')
  ) {
    return 'La respuesta de voz tardó más de lo que el proxy admite. El agente puede haber terminado en el servidor; recarga el chat o reintenta con una pregunta más corta.';
  }
  if (isGatewayUnreachableMessage(raw)) {
    return 'El API Gateway no está en marcha en este equipo. Usa «Iniciar stack» para levantar DuckClaw-DB-Writer y DuckClaw-Gateway (PM2).';
  }
  if (raw === 'Internal Server Error') {
    return 'No se pudo contactar el gateway. Comprueba PM2 o inicia el stack desde el botón de abajo.';
  }
  if (/stt inference failed|stt no disponible/i.test(raw)) {
    return 'No se pudo transcribir el audio. El nodo sensory no decodificó el formato; reintenta tras actualizar.';
  }
  return raw;
}
