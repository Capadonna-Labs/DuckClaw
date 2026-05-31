import assert from 'node:assert/strict';
import { getCsrfTokenFromCookie, mutationHeaders } from './csrfClient';

const store: Record<string, string> = { csrf_token: 'abc123' };

Object.defineProperty(globalThis, 'document', {
  value: {
    get cookie() {
      return Object.entries(store)
        .map(([k, v]) => `${k}=${v}`)
        .join('; ');
    },
  },
  configurable: true,
});

assert.equal(getCsrfTokenFromCookie(), 'abc123');

const postHeaders = mutationHeaders('POST') as Record<string, string>;
assert.equal(postHeaders['X-CSRF-Token'], 'abc123');

const getHeaders = mutationHeaders('GET') as Record<string, string>;
assert.equal(getHeaders['X-CSRF-Token'], undefined);

console.log('csrfClient.test.ts OK');
