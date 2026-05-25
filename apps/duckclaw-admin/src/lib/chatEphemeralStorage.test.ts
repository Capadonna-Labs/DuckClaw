import assert from 'node:assert/strict';
import { mergeEphemeralHeartbeats } from './chatEphemeralStorage';
import type { ChatMsg } from '@/components/chat/types';

const toolA: ChatMsg = {
  role: 'heartbeat',
  text: '🔄 Usando: read_sql',
  heartbeatKind: 'tool',
  toolName: 'read_sql',
  toolPhase: 'done',
};

const toolB: ChatMsg = {
  role: 'heartbeat',
  text: '🔄 Usando: fetch_market_data',
  heartbeatKind: 'tool',
  toolName: 'fetch_market_data',
  toolPhase: 'done',
};

assert.equal(mergeEphemeralHeartbeats([toolA], [toolB]).length, 2);
assert.equal(
  mergeEphemeralHeartbeats(
    [{ ...toolA, toolPhase: 'running' }],
    [{ ...toolA, toolPhase: 'done' }]
  ).length,
  1
);
assert.equal(
  mergeEphemeralHeartbeats([toolA], [toolA, toolB])[0]?.toolPhase,
  'done'
);

console.log('chatEphemeralStorage.test.ts: ok');
