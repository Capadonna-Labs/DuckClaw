/** Parseo de eventos SSE (text/event-stream) desde fetch streaming. */

export type SseChatEvent =
  | { type: 'token'; content: string }
  | {
      type: 'done';
      response: string;
      assigned_worker_id?: string;
      usage_tokens?: Record<string, number>;
      worker_id?: string;
      elapsed_ms?: number;
      figure_base64?: string;
      artifact_id?: string;
      artifact_tenant_id?: string;
    }
  | {
      type: 'heartbeat';
      text: string;
      kind?: 'plan' | 'tool' | 'status' | 'visual';
      worker_id?: string;
      swarm_slot?: number;
      artifact_id?: string;
      artifact_tenant_id?: string;
      tool_name?: string;
      tool_phase?: 'start' | 'done' | 'error';
      elapsed_ms?: number;
    }
  | { type: 'error'; message: string; status?: number }
  | { type: 'terminal' };

function parseDataLine(data: string): SseChatEvent | null {
  const raw = data.trim();
  if (!raw) return null;
  if (raw === '[DONE]') return { type: 'terminal' };
  try {
    const j = JSON.parse(raw) as Record<string, unknown>;
    const t = String(j.type || '');
    if (t === 'token') {
      return { type: 'token', content: String(j.content ?? '') };
    }
    if (t === 'done') {
      return {
        type: 'done',
        response: String(j.response ?? ''),
        assigned_worker_id: j.assigned_worker_id as string | undefined,
        usage_tokens: j.usage_tokens as Record<string, number> | undefined,
        worker_id: j.worker_id as string | undefined,
        elapsed_ms:
          typeof j.elapsed_ms === 'number'
            ? j.elapsed_ms
            : j.elapsed_ms != null
              ? Number(j.elapsed_ms)
              : undefined,
        figure_base64:
          typeof j.figure_base64 === 'string' ? j.figure_base64 : undefined,
        artifact_id: typeof j.artifact_id === 'string' ? j.artifact_id : undefined,
        artifact_tenant_id:
          typeof j.artifact_tenant_id === 'string' ? j.artifact_tenant_id : undefined,
      };
    }
    if (t === 'heartbeat') {
      const kindRaw = String(j.kind || 'status');
      const kind =
        kindRaw === 'plan' ||
        kindRaw === 'tool' ||
        kindRaw === 'status' ||
        kindRaw === 'visual'
          ? kindRaw
          : 'status';
      const swarmSlotRaw = j.swarm_slot;
      const swarm_slot =
        typeof swarmSlotRaw === 'number'
          ? swarmSlotRaw
          : swarmSlotRaw != null
            ? Number(swarmSlotRaw)
            : undefined;
      const toolPhaseRaw = String(j.tool_phase || '').toLowerCase();
      const tool_phase =
        toolPhaseRaw === 'start' || toolPhaseRaw === 'done' || toolPhaseRaw === 'error'
          ? toolPhaseRaw
          : undefined;
      const elapsedRaw = j.elapsed_ms;
      const elapsed_ms =
        typeof elapsedRaw === 'number'
          ? elapsedRaw
          : elapsedRaw != null
            ? Number(elapsedRaw)
            : undefined;
      return {
        type: 'heartbeat',
        text: String(j.text ?? ''),
        kind,
        worker_id: typeof j.worker_id === 'string' ? j.worker_id : undefined,
        swarm_slot: Number.isFinite(swarm_slot) ? Math.max(1, Math.floor(swarm_slot!)) : undefined,
        artifact_id: typeof j.artifact_id === 'string' ? j.artifact_id : undefined,
        artifact_tenant_id:
          typeof j.artifact_tenant_id === 'string' ? j.artifact_tenant_id : undefined,
        tool_name: typeof j.tool_name === 'string' ? j.tool_name : undefined,
        tool_phase,
        elapsed_ms: Number.isFinite(elapsed_ms) ? elapsed_ms : undefined,
      };
    }
    if (t === 'error') {
      return {
        type: 'error',
        message: String(j.message ?? 'Error'),
        status: typeof j.status === 'number' ? j.status : undefined,
      };
    }
  } catch {
    return { type: 'token', content: raw };
  }
  return { type: 'token', content: raw };
}

/** Lee el cuerpo de una respuesta fetch SSE y emite eventos parseados. */
export async function* readSseChatStream(
  body: ReadableStream<Uint8Array> | null,
  signal?: AbortSignal
): AsyncGenerator<SseChatEvent> {
  if (!body) return;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const onAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener('abort', onAbort);
  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        for (const line of block.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const data = line.startsWith('data: ') ? line.slice(6) : line.slice(5).trimStart();
          const ev = parseDataLine(data);
          if (ev) yield ev;
        }
      }
    }
    if (buffer.trim()) {
      for (const line of buffer.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const data = line.startsWith('data: ') ? line.slice(6) : line.slice(5).trimStart();
        const ev = parseDataLine(data);
        if (ev) yield ev;
      }
    }
  } finally {
    signal?.removeEventListener('abort', onAbort);
    reader.releaseLock();
  }
}
