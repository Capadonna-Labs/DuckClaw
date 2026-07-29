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
    const tid = (tenantId || 'default').trim() || 'default';
    const primary = localStorage.getItem(tenantKey('duckclaw-playground-worker', tid))?.trim();
    if (primary) return primary;
    if (tid !== 'default') {
      return localStorage.getItem(tenantKey('duckclaw-playground-worker', 'default'))?.trim() || null;
    }
    return null;
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
    const tid = (tenantId || 'default').trim() || 'default';
    if (tid !== 'default') {
      localStorage.setItem(tenantKey('duckclaw-playground-worker', 'default'), id);
    }
  } catch {
    /* ignore quota */
  }
}

export function readPlaygroundLastLlm(tenantId?: string): PlaygroundLastLlm | null {
  if (typeof window === 'undefined') return null;
  try {
    const tid = (tenantId || 'default').trim() || 'default';
    const raw =
      localStorage.getItem(tenantKey('duckclaw-playground-llm', tid)) ||
      (tid !== 'default' ? localStorage.getItem(tenantKey('duckclaw-playground-llm', 'default')) : null);
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
  const payload = JSON.stringify({ provider, model: llm.model.trim() });
  try {
    localStorage.setItem(tenantKey('duckclaw-playground-llm', tenantId), payload);
    const tid = (tenantId || 'default').trim() || 'default';
    if (tid !== 'default') {
      localStorage.setItem(tenantKey('duckclaw-playground-llm', 'default'), payload);
    }
  } catch {
    /* ignore quota */
  }
}

/** Resolve worker id: tenant last choice beats server "default"; never overwrite localStorage here. */
export function resolvePlaygroundWorkerId(input: {
  initialWorker: string;
  fromServer: string;
  lastWorker: string | null;
  storedWorker: string | null;
  validIds: string[];
}): string {
  const workerOk = (id: string) =>
    Boolean(id.trim() && (input.validIds.includes(id.trim()) || id.trim() === 'default'));
  const initial = input.initialWorker.trim();
  const fromServer = input.fromServer.trim();
  const last = (input.lastWorker || '').trim();
  const stored = (input.storedWorker || '').trim();
  const ids = input.validIds;

  if (initial && workerOk(initial)) return initial;
  if (last && workerOk(last)) return last;
  if (stored && workerOk(stored) && stored !== 'default') return stored;
  if (fromServer && workerOk(fromServer) && fromServer !== 'default') return fromServer;
  if (stored && workerOk(stored)) return stored;
  if (fromServer && workerOk(fromServer)) return fromServer;
  return ids.includes('default') ? 'default' : ids[0] ?? 'default';
}

export function playgroundLlmNeedsRestore(
  server: { provider: string; model: string },
  last: PlaygroundLastLlm | null
): boolean {
  if (!last?.provider.trim()) return false;
  const sp = (server.provider || '').trim();
  const sm = (server.model || '').trim();
  return sp !== last.provider.trim() || sm !== (last.model || '').trim();
}

/** Show last tenant LLM in UI while server/db-writer catches up after stack reload. */
export function mergePlaygroundConfigWithLastLlm<T extends {
  llm?: { provider?: string; model?: string; scope?: string; base_url?: string } | null;
}>(config: T, last: PlaygroundLastLlm | null): T {
  if (!last?.provider.trim()) return config;
  const sp = (config.llm?.provider || '').trim();
  const sm = (config.llm?.model || '').trim();
  if (!playgroundLlmNeedsRestore({ provider: sp, model: sm }, last)) return config;
  return {
    ...config,
    llm: {
      ...(config.llm || {}),
      provider: last.provider.trim(),
      model: (last.model || '').trim(),
      scope: 'chat',
    },
  };
}

export const LLM_SNAPSHOT_SESSION_KEY = 'duckclaw-playground-llm-snapshot';

/** Session snapshot survives full reload after «Reiniciar sistema» (before localStorage is read). */
export function writePlaygroundLlmSnapshot(
  tenantId: string | undefined,
  llm: PlaygroundLastLlm
): void {
  if (typeof window === 'undefined') return;
  const provider = llm.provider.trim();
  if (!provider) return;
  try {
    sessionStorage.setItem(
      LLM_SNAPSHOT_SESSION_KEY,
      JSON.stringify({
        tenantId: (tenantId || 'default').trim() || 'default',
        provider,
        model: llm.model.trim(),
        ts: Date.now(),
      })
    );
  } catch {
    /* ignore */
  }
}

export function consumePlaygroundLlmSnapshot(maxAgeMs = 10 * 60 * 1000): PlaygroundLastLlm | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(LLM_SNAPSHOT_SESSION_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(LLM_SNAPSHOT_SESSION_KEY);
    const parsed = JSON.parse(raw) as {
      provider?: string;
      model?: string;
      ts?: number;
    };
    if (typeof parsed.ts === 'number' && Date.now() - parsed.ts > maxAgeMs) return null;
    const provider = (parsed.provider || '').trim();
    const model = (parsed.model || '').trim();
    if (!provider) return null;
    return { provider, model };
  } catch {
    return null;
  }
}

export const STACK_RELOAD_SESSION_KEY = 'duckclaw-after-stack-reload';

export function markStackReloadPending(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(STACK_RELOAD_SESSION_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function consumeStackReloadPending(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (sessionStorage.getItem(STACK_RELOAD_SESSION_KEY) !== '1') return false;
    sessionStorage.removeItem(STACK_RELOAD_SESSION_KEY);
    return true;
  } catch {
    return false;
  }
}

/** Seed localStorage worker from server when empty. LLM is never backfilled (env default poisons restore). */
export function backfillPlaygroundLastFromServer(
  tenantId: string | undefined,
  server: {
    workerId?: string;
  }
): void {
  const worker = (server.workerId || '').trim();
  if (worker && worker !== 'default' && !readPlaygroundLastWorker(tenantId)) {
    writePlaygroundLastWorker(tenantId, worker);
  }
}
