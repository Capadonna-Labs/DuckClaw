import assert from 'node:assert/strict';
import { describe, expect, it } from 'vitest';

import { resolveIntegrationDocsUrl } from './integrationDocsUrls';
import { isSafeExternalHttpUrl } from './safeExternalHttpUrl';

describe('integration docs urls', () => {
  it('prefers catalog docs_url', () => {
    expect(
      resolveIntegrationDocsUrl({
        id: 'groq',
        docs_url: 'https://console.groq.com/keys',
      })
    ).toBe('https://console.groq.com/keys');
  });

  it('falls back by integration id', () => {
    expect(resolveIntegrationDocsUrl({ id: 'openai', docs_url: null })).toBe(
      'https://platform.openai.com/api-keys'
    );
    expect(resolveIntegrationDocsUrl({ id: 'google', docs_url: '' })).toBe(
      'https://aistudio.google.com/apikey'
    );
  });

  it('rejects unsafe urls', () => {
    assert.equal(isSafeExternalHttpUrl('javascript:alert(1)'), false);
    assert.equal(isSafeExternalHttpUrl('file:///etc/passwd'), false);
    assert.equal(isSafeExternalHttpUrl('https://platform.openai.com/api-keys'), true);
  });
});
