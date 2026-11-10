import { afterEach, expect, it, vi } from 'vitest';
import { clearSavedLoginCredentials, readSavedLoginCredentials, saveSavedLoginCredentials } from './savedLoginCredentials';

afterEach(() => vi.unstubAllGlobals());

it('saves, reads back and clears the login', () => {
  const store = new Map<string, string>();
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  });
  const creds = { email: 'admin@duckclaw.local', password: 'secret12345' };
  saveSavedLoginCredentials(creds);
  expect(readSavedLoginCredentials()).toEqual(creds);
  clearSavedLoginCredentials();
  expect(readSavedLoginCredentials()).toBeNull();
});
