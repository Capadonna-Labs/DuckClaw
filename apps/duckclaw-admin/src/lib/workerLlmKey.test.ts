import { describe, expect, it } from 'vitest';
import { workerLlmKey } from './workerLlmKey';

describe('workerLlmKey', () => {
  it('matches the gateway normalize_runtime_setting_name', () => {
    expect(workerLlmKey('Research-Agent')).toBe('research-agent');
    expect(workerLlmKey('data_analyst')).toBe('data_analyst');
    expect(workerLlmKey(' Youtube Analyst ')).toBe('youtube_analyst');
  });
});
