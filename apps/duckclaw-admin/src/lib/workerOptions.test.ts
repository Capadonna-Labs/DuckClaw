import assert from 'node:assert/strict';
import { stripChatIdentityNoise, workerMatches } from './workerOptions';

const cotLine = 'Worker A 5 · Viernes 24-Jul 09:41 COT\n\n📈 BTC < $64K';
const kept = stripChatIdentityNoise(cotLine, {
  displayName: 'Worker A 5',
  workerId: 'worker-a',
});
assert.match(kept, /^Worker A 5 · Viernes 24-Jul 09:41 COT/);
assert.doesNotMatch(kept, /^·/);

const legacy = stripChatIdentityNoise('Worker A 5\n\nRespuesta', {
  displayName: 'Worker A 5',
});
assert.equal(legacy, 'Respuesta');

assert.equal(workerMatches('quant_analyst', 'quant_analyst'), true);
assert.equal(workerMatches('quant_analyst->quant-trader', 'quant_analyst'), true);
assert.equal(workerMatches('quant_analyst', 'quant_analyst->quant-trader'), true);
assert.equal(workerMatches('quant_analyst->quant-trader', 'quant_reporter'), false);

console.log('workerOptions.test.ts OK');
