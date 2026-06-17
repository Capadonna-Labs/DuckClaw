import assert from 'node:assert/strict';
import {
  filterEphemeralForWorker,
  mergeEphemeralHeartbeats,
} from './chatEphemeralStorage';
import { workerMatches } from './workerOptions';
import type { ChatMsg } from '@/components/chat/types';

const toolA: ChatMsg = {
  role: 'heartbeat',
  text: 'Usando: read_sql',
  heartbeatKind: 'tool',
  toolName: 'read_sql',
  toolPhase: 'done',
};

const toolB: ChatMsg = {
  role: 'heartbeat',
  text: 'Usando: fetch_market_data',
  heartbeatKind: 'tool',
  toolName: 'fetch_market_data',
  toolPhase: 'done',
};

const toolB2: ChatMsg = {
  role: 'heartbeat',
  text: '🔄 Usando: fetch_market_data',
  heartbeatKind: 'tool',
  toolName: 'fetch_market_data',
  toolInvocationId: 'fetch_market_data-2',
  toolPhase: 'done',
};

assert.equal(mergeEphemeralHeartbeats([toolA], [toolB]).length, 2);
assert.equal(mergeEphemeralHeartbeats([toolA], [toolB, toolB2]).length, 3);
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

assert.ok(workerMatches('UiDesignerWorker', 'ui-designer'));
assert.ok(workerMatches('platform-orchestrator', 'PlatformOrchestratorWorker'));

const orchestratorHb: ChatMsg = {
  ...toolA,
  workerId: 'platform-orchestrator',
  toolName: 'list_categories',
};
const designerHb: ChatMsg = {
  ...toolB,
  workerId: 'UiDesignerWorker',
};
const filtered = filterEphemeralForWorker([orchestratorHb, designerHb], 'UiDesignerWorker');
assert.equal(filtered.length, 1);
assert.equal(filtered[0]?.toolName, 'fetch_market_data');

console.log('chatEphemeralStorage.test.ts: ok');
