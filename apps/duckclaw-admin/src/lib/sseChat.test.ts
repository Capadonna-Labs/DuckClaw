import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { readSseChatStream } from './sseChat';

const enc = new TextEncoder();

describe('readSseChatStream', () => {
  it('parses data events', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(enc.encode('data: {"type":"token","content":"ok"}\n\n'));
        controller.close();
      },
    });
    const events = [];
    for await (const ev of readSseChatStream(stream)) events.push(ev);
    assert.deepEqual(events, [{ type: 'token', content: 'ok' }]);
  });

  it('times out comment-only streams', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(enc.encode(': keepalive\n\n'));
      },
    });
    const iter = readSseChatStream(stream, undefined, { eventIdleTimeoutMs: 5 });
    await assert.rejects(() => iter.next(), /SSE sin actividad/);
  });
});
