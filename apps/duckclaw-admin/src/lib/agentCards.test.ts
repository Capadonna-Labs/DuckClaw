import assert from 'node:assert/strict';
import { agentCardSubtitle, agentDescription, agentMetadata, agentWorkerIcon } from './agentCards';

assert.equal(
  agentDescription({
    id: 'research_worker',
    name: 'ResearchWorker',
    description: 'Descripción cargada desde manifest.yaml',
    schema_name: 'research_worker',
  }),
  'Descripción cargada desde manifest.yaml'
);

assert.equal(
  agentDescription({ id: 'bare_worker', name: 'BareWorker' }),
  ''
);

assert.equal(
  agentCardSubtitle({
    id: 'research_worker',
    name: 'ResearchWorker',
    skills_list: ['rag_search', 'web_fetch', 'code_exec', 'notify'],
  }),
  '4 skills: rag_search, web_fetch, code_exec +1'
);

assert.equal(agentWorkerIcon('devops'), agentWorkerIcon('devops'));
assert.notEqual(agentWorkerIcon('devops'), agentWorkerIcon('research_worker'));

assert.deepEqual(
  agentMetadata({ id: 'research_worker', name: 'ResearchWorker', schema_name: 'research_worker', temperature: 0.3 }),
  [{ label: 'Temp', value: '0.3' }]
);

assert.deepEqual(
  agentMetadata({ id: 'team-lead', name: 'Team Lead', schema_name: 'team_lead_worker' }),
  [{ label: 'Schema', value: 'axis_maestro_worker' }]
);

console.log('agentCards.test.ts: ok');
