import assert from 'node:assert/strict';
import {
  hasToolHeartbeatInCurrentTurn,
  isThinkingStatusHeartbeat,
  shouldSkipEmptyStreamingAssistant,
  stripThinkingStatusHeartbeats,
} from './useAdminChat';
import type { ChatMsg } from './types';

const messages: ChatMsg[] = [
  { role: 'user', text: 'hola' },
  { role: 'heartbeat', text: 'Pensando…', heartbeatKind: 'status' },
  { role: 'heartbeat', text: 'read_sql — en curso', heartbeatKind: 'tool', toolName: 'read_sql' },
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

const emptyStreamingAssistant = messages[3];
assert.equal(
  shouldSkipEmptyStreamingAssistant(emptyStreamingAssistant, messages),
  true,
  'skip empty assistant bubble when tool heartbeats are in the current turn'
);
assert.equal(
  shouldSkipEmptyStreamingAssistant(
    { role: 'assistant', text: '', streaming: true },
    [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: '', streaming: true },
    ]
  ),
  false,
  'keep empty assistant path when no tool heartbeats (ThinkingBubble handles UI)'
);
assert.equal(
  shouldSkipEmptyStreamingAssistant(
    { role: 'assistant', text: 'partial', streaming: true },
    messages
  ),
  false,
  'do not skip assistant with text'
);
assert.equal(
  shouldSkipEmptyStreamingAssistant(
    {
      role: 'assistant',
      text: '',
      streaming: true,
      imagePreviews: [{ url: '/x.png', name: 'chart' }],
    },
    messages
  ),
  false,
  'do not skip empty streaming assistant when image previews exist'
);

console.log('useAdminChatThinking.test.ts: ok');
