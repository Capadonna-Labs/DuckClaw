import assert from 'node:assert/strict';
import type { ChatMsg } from '@/components/chat/types';
import {
  createToolInvocationId,
  findRunningToolHeartbeatIndex,
  parseToolNameFromHeartbeatText,
} from './toolHeartbeat';

assert.equal(parseToolNameFromHeartbeatText('Usando: read_sql · 3ms'), 'read_sql');
assert.equal(parseToolNameFromHeartbeatText('\u{1F504} Usando: read_sql · \u23F1\uFE0F 3ms'), 'read_sql');
assert.equal(
  parseToolNameFromHeartbeatText('\u{1F504} Paso actual: llamo a la herramienta run_browser_sandbox…'),
  'run_browser_sandbox'
);
assert.equal(parseToolNameFromHeartbeatText(''), null);

const id1 = createToolInvocationId('fetch_market_data');
const id2 = createToolInvocationId('fetch_market_data');
assert.notEqual(id1, id2);

const msgs: ChatMsg[] = [
  {
    role: 'heartbeat',
    heartbeatKind: 'tool',
    toolName: 'get_current_time',
    toolInvocationId: 'gct-1',
    toolPhase: 'done',
    text: '🔄 Usando: get_current_time',
  },
  {
    role: 'heartbeat',
    heartbeatKind: 'tool',
    toolName: 'fetch_market_data',
    toolInvocationId: 'fmd-1',
    toolPhase: 'done',
    text: '🔄 Usando: fetch_market_data',
  },
  {
    role: 'heartbeat',
    heartbeatKind: 'tool',
    toolName: 'fetch_market_data',
    toolInvocationId: 'fmd-2',
    toolPhase: 'running',
    text: '🔄 Usando: fetch_market_data',
  },
];

assert.equal(findRunningToolHeartbeatIndex(msgs, 'fetch_market_data', msgs.length), 2);
assert.equal(findRunningToolHeartbeatIndex(msgs, 'get_current_time', msgs.length), -1);
assert.equal(findRunningToolHeartbeatIndex(msgs, 'fetch_market_data', 2), 1);

console.log('toolHeartbeat.test.ts: ok');
