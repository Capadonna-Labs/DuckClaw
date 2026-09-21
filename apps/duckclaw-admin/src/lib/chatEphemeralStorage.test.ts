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

assert.equal(
  mergeEphemeralHeartbeats(
    [
      {
        role: 'heartbeat',
        heartbeatKind: 'status',
        text: "Worker 'quant_analyst' not found in catalog for tenant 'user-x'",
      },
    ],
    [toolA]
  ).length,
  1,
  'catalog-miss PROGRESO heartbeats are not persisted in ephemeral merge'
);
assert.equal(
  mergeEphemeralHeartbeats(
    [
      {
        role: 'heartbeat',
        heartbeatKind: 'status',
        text: "Worker 'quant_analyst' not found in catalog for tenant 'user-x'",
      },
    ],
    [toolA]
  )[0]?.toolName,
  'read_sql'
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

// Nested invoke_worker labels must stay with the caller worker.
const nestedHb: ChatMsg = {
  ...toolA,
  workerId: 'quant_analyst->quant-trader',
  toolName: 'propose_trade_signal',
};
assert.equal(workerMatches('quant_analyst->quant-trader', 'quant_analyst'), true);
assert.equal(workerMatches('quant_analyst', 'quant_analyst->quant-trader'), true);
assert.equal(workerMatches('quant_analyst->quant-trader', 'quant_reporter'), false);
const nestedKept = filterEphemeralForWorker(
  [orchestratorHb, nestedHb],
  'quant_analyst'
);
assert.equal(nestedKept.length, 1);
assert.equal(nestedKept[0]?.toolName, 'propose_trade_signal');

console.log('chatEphemeralStorage.test.ts: ok');
