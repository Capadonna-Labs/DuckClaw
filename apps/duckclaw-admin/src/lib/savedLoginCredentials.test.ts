import assert from 'node:assert/strict';
import {
  clearSavedLoginCredentials,
  readSavedLoginCredentials,
  saveSavedLoginCredentials,
} from './savedLoginCredentials';

const store = new Map<string, string>();
(globalThis as typeof globalThis & { window: Window }).window = {
  localStorage: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
  },
} as unknown as Window;

const creds = { email: 'admin@duckclaw.local', password: 'secret12345' };
saveSavedLoginCredentials(creds);
assert.deepEqual(readSavedLoginCredentials(), creds);
clearSavedLoginCredentials();
assert.equal(readSavedLoginCredentials(), null);

console.log('savedLoginCredentials.test.ts: ok');
