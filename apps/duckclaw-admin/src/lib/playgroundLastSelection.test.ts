import { describe, expect, it } from 'vitest';

import {
  mergePlaygroundConfigWithLastLlm,
  playgroundLlmNeedsRestore,
  resolvePlaygroundWorkerId,
} from './playgroundLastSelection';

describe('resolvePlaygroundWorkerId', () => {
  const ids = ['default', 'worker-alpha', 'analytics-worker'];

  it('prefers tenant last worker over server default', () => {
    expect(
      resolvePlaygroundWorkerId({
        initialWorker: '',
        fromServer: 'default',
        lastWorker: 'worker-alpha',
        storedWorker: null,
        validIds: ids,
      })
    ).toBe('worker-alpha');
  });

  it('prefers tenant last worker over server non-default', () => {
    expect(
      resolvePlaygroundWorkerId({
        initialWorker: '',
        fromServer: 'analytics-worker',
        lastWorker: 'worker-alpha',
        storedWorker: null,
        validIds: ids,
      })
    ).toBe('worker-alpha');
  });

  it('uses server worker when no tenant last choice', () => {
    expect(
      resolvePlaygroundWorkerId({
        initialWorker: '',
        fromServer: 'analytics-worker',
        lastWorker: null,
        storedWorker: null,
        validIds: ids,
      })
    ).toBe('analytics-worker');
  });
});

describe('playgroundLlmNeedsRestore', () => {
  it('detects mismatch with last llm', () => {
    expect(
      playgroundLlmNeedsRestore(
        { provider: 'openrouter', model: 'z-ai/glm-5.2' },
        { provider: 'mlx', model: 'gemma4-e4b' }
      )
    ).toBe(true);
  });

  it('skips when already aligned', () => {
    expect(
      playgroundLlmNeedsRestore(
        { provider: 'mlx', model: 'gemma4-e4b' },
        { provider: 'mlx', model: 'gemma4-e4b' }
      )
    ).toBe(false);
  });
});

describe('mergePlaygroundConfigWithLastLlm', () => {
  it('overlays last llm when server shows env default', () => {
    const merged = mergePlaygroundConfigWithLastLlm(
      {
        llm: { provider: 'openrouter', model: 'z-ai/glm-4.9b', scope: 'env_bootstrap' },
      },
      { provider: 'mlx', model: 'gemma4-e4b' }
    );
    expect(merged.llm?.provider).toBe('mlx');
    expect(merged.llm?.model).toBe('gemma4-e4b');
    expect(merged.llm?.scope).toBe('chat');
  });
});
