import assert from 'node:assert/strict';
import { parseToolNameFromHeartbeatText } from './toolHeartbeat';

assert.equal(parseToolNameFromHeartbeatText('🔄 Usando: read_sql · ⏱️ 3ms'), 'read_sql');
assert.equal(
  parseToolNameFromHeartbeatText('🔄 Paso actual: llamo a la herramienta run_browser_sandbox…'),
  'run_browser_sandbox'
);
assert.equal(parseToolNameFromHeartbeatText(''), null);

console.log('toolHeartbeat.test.ts: ok');
