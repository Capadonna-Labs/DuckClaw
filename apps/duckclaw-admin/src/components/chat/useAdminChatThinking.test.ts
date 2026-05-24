import assert from 'node:assert/strict';
import {
  hasToolHeartbeatInCurrentTurn,
  isThinkingStatusHeartbeat,
  stripThinkingStatusHeartbeats,
} from './useAdminChat';
import type { ChatMsg } from './types';

const messages: ChatMsg[] = [
  { role: 'user', text: 'hola' },
  { role: 'heartbeat', text: 'Pensando…', heartbeatKind: 'status' },
  { role: 'heartbeat', text: '🔄 read_sql — en curso', heartbeatKind: 'tool', toolName: 'read_sql' },
  { role: 'assistant', text: '', streaming: true },
];

assert.equal(isThinkingStatusHeartbeat(messages[1]), true);
assert.equal(isThinkingStatusHeartbeat(messages[2]), false);
assert.equal(hasToolHeartbeatInCurrentTurn(messages), true);
assert.equal(
  hasToolHeartbeatInCurrentTurn([
    { role: 'user', text: 'hola' },
    { role: 'assistant', text: '', streaming: true },
  ]),
  false
);
assert.deepEqual(stripThinkingStatusHeartbeats(messages), [
  messages[0],
  messages[2],
  { role: 'assistant', text: '', streaming: true },
]);

console.log('useAdminChatThinking.test.ts: ok');
