import assert from 'node:assert/strict';
import { bffGatewayTimeoutMs } from './bffGatewayTimeouts';

assert.equal(bffGatewayTimeoutMs('health', 'GET'), 3_000);
assert.equal(bffGatewayTimeoutMs('bootstrap/status', 'GET'), 3_000);
assert.equal(bffGatewayTimeoutMs('playground/config', 'GET'), 8_000);
assert.equal(bffGatewayTimeoutMs('knowledge/sources', 'POST'), 120_000);
assert.equal(bffGatewayTimeoutMs('templates/devops', 'GET'), 30_000);
assert.equal(bffGatewayTimeoutMs('templates/devops', 'PUT'), 45_000);
assert.equal(bffGatewayTimeoutMs('ops/run', 'POST'), 60_000);

console.log('bffGatewayTimeouts.test.ts OK');
