import assert from 'node:assert/strict';
import { agentDescription, agentMetadata } from './agentCards';

assert.equal(
  agentDescription({
    id: 'research_worker',
    name: 'ResearchWorker',
    description: 'Descripción cargada desde manifest.yaml',
    schema_name: 'research_worker',
  }),
  'Descripción cargada desde manifest.yaml'
);

assert.deepEqual(
  agentMetadata({ id: 'research_worker', name: 'ResearchWorker', schema_name: 'research_worker', temperature: 0.3 }),
  [{ label: 'Temp', value: '0.3' }]
);

assert.deepEqual(
  agentMetadata({ id: 'axis-maestro', name: 'AXIS Maestro', schema_name: 'axis_maestro_worker' }),
  [{ label: 'Schema', value: 'axis_maestro_worker' }]
);

console.log('agentCards.test.ts: ok');
