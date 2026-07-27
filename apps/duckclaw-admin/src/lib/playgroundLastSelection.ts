/** Last playground worker + LLM per tenant (survives stack restart / full reload). */

export type PlaygroundLastLlm = {
  provider: string;
  model: string;
};

function tenantKey(prefix: string, tenantId?: string): string {
  const tid = (tenantId || 'default').trim() || 'default';
  return `${prefix}:${tid}`;
}

export function readPlaygroundLastWorker(tenantId?: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(tenantKey('duckclaw-playground-worker', tenantId))?.trim() || null;
  } catch {
    return null;
  }
}

export function writePlaygroundLastWorker(tenantId: string | undefined, workerId: string): void {
  if (typeof window === 'undefined') return;
  const id = workerId.trim();
  if (!id) return;
  try {
    localStorage.setItem(tenantKey('duckclaw-playground-worker', tenantId), id);
  } catch {
    /* ignore quota */
  }
}

export function readPlaygroundLastLlm(tenantId?: string): PlaygroundLastLlm | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(tenantKey('duckclaw-playground-llm', tenantId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PlaygroundLastLlm;
    const provider = (parsed?.provider || '').trim();
    const model = (parsed?.model || '').trim();
    if (!provider) return null;
    return { provider, model };
  } catch {
    return null;
  }
}

export function writePlaygroundLastLlm(
  tenantId: string | undefined,
  llm: PlaygroundLastLlm
): void {
  if (typeof window === 'undefined') return;
  const provider = llm.provider.trim();
  if (!provider) return;
  try {
    localStorage.setItem(
      tenantKey('duckclaw-playground-llm', tenantId),
      JSON.stringify({ provider, model: llm.model.trim() })
    );
  } catch {
    /* ignore quota */
  }
}
