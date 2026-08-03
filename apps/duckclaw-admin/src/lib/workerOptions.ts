/** Worker en config del gateway: string legacy o { id, label }. */
export type WorkerOption = string | { id: string; label: string };

export function workerOptionId(w: WorkerOption): string {
  return typeof w === 'string' ? w : w.id;
}

export function workerOptionLabel(w: WorkerOption): string {
  return typeof w === 'string' ? w : w.label || w.id;
}

export function workerOptionIds(workers: WorkerOption[] | undefined): string[] {
  return (workers ?? []).map(workerOptionId);
}

export function workersInclude(workers: WorkerOption[] | undefined, id: string): boolean {
  if (!id) return false;
  return workerOptionIds(workers).includes(id);
}

/**
 * Nombre visible para UI. Vacío si solo hay id técnico (evita pintar `d` / slugs crudos).
 */
export function resolveWorkerDisplayName(
  workers: WorkerOption[] | undefined,
  workerId: string | undefined
): string {
  const id = (workerId || '').trim();
  if (!id) return '';
  const match = (workers ?? []).find((w) => workerOptionId(w) === id);
  if (!match) return '';
  const label = workerOptionLabel(match).trim();
  if (!label || label === id) return '';
  return label;
}

/** Etiqueta de identidad en chat: solo nombre visible. Sin slot swarm. */
export function formatChatIdentityPrefix(displayName?: string): string {
  const label = (displayName || '').trim();
  return label || 'Agente';
}

/**
 * Quita prefijos de identidad legacy del cuerpo del mensaje
 * (`d 1`, `devops 1`, `Agente 1`, markdown bold, etc.).
 */
export function stripChatIdentityNoise(
  text: string,
  options?: {
    workerId?: string;
    displayName?: string;
  }
): string {
  let body = (text || '').trim();
  if (!body) return body;

  const tokens = [options?.displayName, options?.workerId]
    .map((t) => (t || '').trim())
    .filter(Boolean);

  for (const token of tokens) {
    const esc = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const plainCotHeader = new RegExp(`^${esc}(?:\\s+\\d+)?\\s*·[^\\n]*\\bCOT\\b`, 'iu');
    // Encabezado Caveman plano: no partir el nombre del timestamp (deja «· … COT» huérfano).
    if (plainCotHeader.test(body)) {
      continue;
    }
    body = body
      .replace(new RegExp(`^\\*\\*${esc}(?:\\s+\\d+)?\\s*·[^*]+\\*\\*\\s*`, 'iu'), '')
      .replace(new RegExp(`^${esc}(?:\\s+\\d+)?(?:\\s*[—–-]\\s*)?`, 'u'), '')
      .trim();
  }

  body = body.replace(/^Agente(?:\s+\d+)?(?:\s*[—–-]\s*)?/u, '').trim();

  // Mensaje que es SOLO "{id|slug} {slot}" (p. ej. "d 1") → vacío.
  if (/^[^\s]{1,64}\s+\d+$/u.test(body)) {
    return '';
  }

  // Primera línea solo identidad técnica + slot, resto del mensaje debajo.
  body = body.replace(/^[^\s]{1,64}\s+\d+\s*\n+/u, '').trim();

  return body;
}

/** Clave canónica para emparejar workers (aliases legacy incluidos). */
export function normalizeWorkerKey(id: string): string {
  const slug = id.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!slug) return '';
  if (slug === 'platformorchestrator' || slug === 'platformorchestratorworker') {
    return 'platform-orchestrator';
  }
  if (slug === 'uidesigner' || slug === 'uidesignerworker') {
    return 'ui-designer';
  }
  return slug;
}

/** True si ambos ids refieren al mismo worker (aliases incluidos). */
export function workerMatches(a: string, b: string): boolean {
  const ka = normalizeWorkerKey(a);
  const kb = normalizeWorkerKey(b);
  if (!ka || !kb) return true;
  return ka === kb;
}
