import assert from 'node:assert/strict';
import {
  BFF_SESSION_STALE_GRACE_MS,
  BFF_SESSION_TTL_MS,
  coalesceBffSessionLookup,
  getCachedBffSession,
  invalidateBffSessionCache,
  resetBffSessionCacheForTests,
  setCachedBffSession,
} from './bffSessionCache';

resetBffSessionCacheForTests();

const user = {
  id: 'u1',
  email: 'a@b.com',
  nombre: 'A',
  rol: 'admin',
};

setCachedBffSession('sess-1', user);
assert.equal(getCachedBffSession('sess-1')?.email, 'a@b.com');

invalidateBffSessionCache('sess-1');
assert.equal(getCachedBffSession('sess-1'), undefined);

assert.ok(BFF_SESSION_TTL_MS >= 30_000);
assert.ok(BFF_SESSION_STALE_GRACE_MS >= 60_000);

setCachedBffSession('sess-stale', user);
const staleOnly = getCachedBffSession('sess-stale', { allowStale: true });
assert.equal(staleOnly?.email, 'a@b.com');

let calls = 0;
const gate = Promise.resolve();
const p1 = coalesceBffSessionLookup('sess-2', async () => {
  calls += 1;
  await gate;
  return user;
});
const p2 = coalesceBffSessionLookup('sess-2', async () => {
  calls += 1;
  return user;
});
assert.equal(p1, p2);
void p1.then(() => {
  assert.equal(calls, 1);
  console.log('bffSessionCache.test.ts OK');
});
