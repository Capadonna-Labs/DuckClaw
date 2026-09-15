import assert from 'node:assert/strict';
import { bffGatewayTimeoutMs } from './bffGatewayTimeouts';

assert.equal(bffGatewayTimeoutMs('health', 'GET'), 10_000);
assert.equal(bffGatewayTimeoutMs('bootstrap/status', 'GET'), 10_000);
assert.equal(bffGatewayTimeoutMs('playground/config', 'GET'), 30_000);
assert.equal(bffGatewayTimeoutMs('knowledge/sources', 'POST'), 120_000);
assert.equal(bffGatewayTimeoutMs('templates/devops', 'GET'), 30_000);
assert.equal(bffGatewayTimeoutMs('templates/devops', 'PUT'), 45_000);
assert.equal(bffGatewayTimeoutMs('ops/run', 'POST'), 240_000);
assert.equal(bffGatewayTimeoutMs('chat/suggestions', 'POST'), 120_000);
assert.equal(bffGatewayTimeoutMs('chat/suggestions/auto', 'POST'), 120_000);

console.log('bffGatewayTimeouts.test.ts OK');
