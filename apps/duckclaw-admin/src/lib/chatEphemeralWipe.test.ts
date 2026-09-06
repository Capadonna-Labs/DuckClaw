import { describe, expect, it, beforeEach } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import {
  readEphemeralHeartbeats,
  writeEphemeralHeartbeats,
} from './chatEphemeralStorage';

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  Object.defineProperty(globalThis, 'window', {
    value: globalThis,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'sessionStorage', {
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      get length() {
        return store.size;
      },
      key: (i: number) => [...store.keys()][i] ?? null,
    },
    configurable: true,
  });
});

const tool = (name: string): ChatMsg => ({
  role: 'heartbeat',
  heartbeatKind: 'tool',
  toolName: name,
  toolPhase: 'done',
  text: `Usando: ${name}`,
  workerId: 'worker-a',
});

describe('writeEphemeralHeartbeats empty guard', () => {
  it('does not wipe stored tools when messages is empty', () => {
    const chatId = 'admin-conv-test';
    writeEphemeralHeartbeats(chatId, 'worker-a', [
      { role: 'user', text: 'hola' },
      tool('web_search'),
      { role: 'assistant', text: 'ok' },
    ]);
    expect(readEphemeralHeartbeats(chatId, 'worker-a')).toHaveLength(1);

    writeEphemeralHeartbeats(chatId, 'worker-a', []);
    expect(readEphemeralHeartbeats(chatId, 'worker-a')).toHaveLength(1);
  });

  it('reads legacy key when worker key missing', () => {
    const chatId = 'admin-conv-legacy';
    writeEphemeralHeartbeats(chatId, '', [tool('read_sql')]);
    expect(readEphemeralHeartbeats(chatId, 'worker-a')).toHaveLength(1);
  });

  it('keeps heartbeats whose gateway worker_id differs from the UI worker', () => {
    const chatId = 'admin-conv-mismatch';
    const hb: ChatMsg = { ...tool('tavily_search'), workerId: 'agent-1726618406' };
    writeEphemeralHeartbeats(chatId, 'worker-a', [
      { role: 'user', text: 'busca noticias' },
      hb,
      { role: 'assistant', text: 'listo' },
    ]);
    expect(readEphemeralHeartbeats(chatId, 'worker-a')).toHaveLength(1);
  });

  it('does not wipe stored tools when history has no heartbeats', () => {
    const chatId = 'admin-conv-no-wipe';
    writeEphemeralHeartbeats(chatId, 'worker-a', [
      { role: 'user', text: 'hola' },
      tool('web_search'),
      { role: 'assistant', text: 'ok' },
    ]);
    writeEphemeralHeartbeats(chatId, 'Worker-A', [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: 'ok' },
    ]);
    expect(readEphemeralHeartbeats(chatId, 'Worker-A')).toHaveLength(1);
  });
});
