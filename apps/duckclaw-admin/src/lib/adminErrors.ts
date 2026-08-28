/** Mensajes legibles cuando el BFF no alcanza el gateway. */

function isDesktopRuntime(): boolean {
  return (
    (process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP || '').trim() === '1' ||
    (process.env.LITE_MODE || '').trim() === '1'
  );
}

function desktopGatewayDownMessage(): string {
  return 'El gateway embebido no responde. Cierra DuckClaw por completo y ábrelo de nuevo, o usa «Reiniciar sistema» en la barra superior.';
}

function hostGatewayDownMessage(): string {
  return 'El API Gateway no está en marcha en este equipo. Usa «Iniciar stack» para levantar DuckClaw-DB-Writer y DuckClaw-Gateway (PM2).';
}

export function isConversationNotFoundError(err: unknown): boolean {
  const m = (err instanceof Error ? err.message : String(err || '')).toLowerCase();
  return m.includes('conversación no encontrada') || m.includes('conversacion no encontrada');
}

export function isGatewayUnreachableMessage(message: string): boolean {
  const m = message.toLowerCase();
  if (
    m.includes('timeout') ||
    m.includes('timed out') ||
    m.includes('tardó demasiado') ||
    m.includes('aborted due to timeout') ||
    m.includes('no respondió') ||
    m.includes('no respondio')
  ) {
    return false;
  }
  return (
    m.includes('fetch failed') ||
    m.includes('econnrefused') ||
    m.includes('failed to fetch') ||
    m.includes('network') ||
    m.includes('no responde') ||
    m.includes('gateway no') ||
    m.includes('503')
  );
}

function looksLikeProblemContext(value: string): boolean {
  return /^[a-z][a-z0-9_.:-]{2,64}$/i.test(value) && !value.includes(' ');
}

/** Extrae mensaje legible de respuestas FastAPI (detail string u objeto RFC7807). */
export function parseApiErrorDetail(data: unknown, status = 500): string {
  if (!data || typeof data !== 'object') return `Error ${status}`;
  const root = data as Record<string, unknown>;
  if (typeof root.detail === 'string') return root.detail;
  if (root.detail && typeof root.detail === 'object') {
    const inner = root.detail as Record<string, unknown>;
    if (
      typeof inner.title === 'string' &&
      typeof inner.detail === 'string' &&
      looksLikeProblemContext(inner.detail)
    ) {
      return inner.title;
    }
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
    m.includes('aborted due to timeout') ||
    m.includes('no respondió') ||
    m.includes('no respondio')
  ) {
    if (m.includes('voz') || m.includes('voice')) {
      return 'La respuesta de voz tardó más de lo que el proxy admite. El agente puede haber terminado en el servidor; recarga el chat o reintenta con una pregunta más corta.';
    }
    return 'El gateway tardó demasiado. Recarga el historial; el stack ya está en marcha.';
  }
  if (isGatewayUnreachableMessage(raw)) {
    return isDesktopRuntime() ? desktopGatewayDownMessage() : hostGatewayDownMessage();
  }
  if (raw === 'Internal Server Error') {
    return isDesktopRuntime()
      ? desktopGatewayDownMessage()
      : 'No se pudo contactar el gateway. Comprueba PM2 o inicia el stack desde el botón de abajo.';
  }
  if (/stt inference failed|stt no disponible/i.test(raw)) {
    return 'No se pudo transcribir el audio. El nodo sensory no decodificó el formato; reintenta tras actualizar.';
  }
  if (/procesando imagen|vlm|connecttimeout.*8081/i.test(m)) {
    return 'No se pudo analizar la imagen (Mac mini / MLX fuera de línea). El mensaje de texto puede seguir; reintenta cuando Tailscale muestre el Mac activo.';
  }
  return raw;
}
