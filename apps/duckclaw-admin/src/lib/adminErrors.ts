/** Mensajes legibles cuando el BFF no alcanza el gateway. */

export function isGatewayUnreachableMessage(message: string): boolean {
  const m = message.toLowerCase();
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

export function friendlyGatewayError(raw: string): string {
  if (isGatewayUnreachableMessage(raw)) {
    return 'El API Gateway no está en marcha en este equipo. Usa «Iniciar stack» para levantar DuckClaw-DB-Writer y DuckClaw-Gateway (PM2).';
  }
  if (raw === 'Internal Server Error') {
    return 'No se pudo contactar el gateway. Comprueba PM2 o inicia el stack desde el botón de abajo.';
  }
  return raw;
}
