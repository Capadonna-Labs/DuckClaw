import { describe, expect, it } from 'vitest';
import { workerLlmKey } from './workerLlmKey';

describe('workerLlmKey', () => {
  it('matches the gateway normalize_runtime_setting_name', () => {
    expect(workerLlmKey('Quant-Trader')).toBe('quant-trader');
    expect(workerLlmKey('quant_analyst')).toBe('quant_analyst');
    expect(workerLlmKey(' Youtube Analyst ')).toBe('youtube_analyst');
  });
});
