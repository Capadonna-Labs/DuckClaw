import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { bffGatewayTimeoutMs } from './bffGatewayTimeouts';

describe('bffGatewayTimeoutMs', () => {
  it('maps health and bootstrap to the health tier', () => {
    assert.equal(bffGatewayTimeoutMs('health', 'GET'), 10_000);
    assert.equal(bffGatewayTimeoutMs('bootstrap/status', 'GET'), 10_000);
  });

  it('keeps playground and knowledge mutation tiers', () => {
    assert.equal(bffGatewayTimeoutMs('playground/config', 'GET'), 30_000);
    assert.equal(bffGatewayTimeoutMs('knowledge/sources', 'POST'), 120_000);
    assert.equal(bffGatewayTimeoutMs('templates/devops', 'GET'), 30_000);
    assert.equal(bffGatewayTimeoutMs('templates/devops', 'PUT'), 45_000);
  });

  it('gives ops/run a long timeout', () => {
    assert.equal(bffGatewayTimeoutMs('ops/run', 'POST'), 240_000);
  });

  it('gives chat suggestions 120s so post-turn LLM chips survive load', () => {
    assert.equal(bffGatewayTimeoutMs('chat/suggestions', 'POST'), 120_000);
    assert.equal(bffGatewayTimeoutMs('chat/suggestions/auto', 'POST'), 120_000);
  });
});
