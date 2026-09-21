import { afterEach, describe, expect, it, vi } from 'vitest';
import { readSseChatStream } from '@/lib/sseChat';
import { SseIdleTimeoutError } from '@/lib/sseIdle';

function sseBody(chunks: Uint8Array[], hangMs?: number): ReadableStream<Uint8Array> {
  let i = 0;
  return new ReadableStream({
    async pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(chunks[i++]);
        return;
      }
      if (hangMs != null && hangMs > 0) {
        await new Promise((r) => setTimeout(r, hangMs));
      }
      controller.close();
    },
  });
}

describe('readSseChatStream idle timeout', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('parses data events', async () => {
    const enc = new TextEncoder();
    const body = sseBody([
      enc.encode('data: {"type":"token","content":"hola"}\n\n'),
      enc.encode('data: [DONE]\n\n'),
    ]);
    const events = [];
    for await (const ev of readSseChatStream(body, undefined, { idleTimeoutMs: 5_000 })) {
      events.push(ev);
    }
    expect(events).toEqual([
      { type: 'token', content: 'hola' },
      { type: 'terminal' },
    ]);
  });

  it('throws SseIdleTimeoutError when no bytes arrive', async () => {
    vi.useFakeTimers();
    const body = new ReadableStream<Uint8Array>({
      pull() {
        /* never enqueue — hang forever */
      },
    });
    const iter = readSseChatStream(body, undefined, { idleTimeoutMs: 1_000 });
    const nextP = iter.next();
    const rejection = expect(nextP).rejects.toBeInstanceOf(SseIdleTimeoutError);
    await vi.advanceTimersByTimeAsync(1_000);
    await rejection;
  });
});
