import { describe, expect, it } from 'vitest';
import { formatCompactTokenCount, inferModelContextWindow } from './modelContextWindow';

describe('inferModelContextWindow', () => {
  it('resolves common Claude / GPT windows', () => {
    expect(inferModelContextWindow('claude-sonnet-4-20250514')).toBe(1_000_000);
    expect(inferModelContextWindow('claude-3-5-sonnet-latest')).toBe(200_000);
    expect(inferModelContextWindow('gpt-4o-mini')).toBe(128_000);
    expect(inferModelContextWindow('unknown-local-gguf')).toBeNull();
    expect(inferModelContextWindow('')).toBeNull();
  });

  it('uses 1M for DeepSeek V4 and 128k for legacy DeepSeek', () => {
    expect(inferModelContextWindow('deepseek/deepseek-v4-flash')).toBe(1_000_000);
    expect(inferModelContextWindow('deepseek/deepseek-v4-pro')).toBe(1_000_000);
    expect(inferModelContextWindow('deepseek-v4-flash')).toBe(1_000_000);
    expect(inferModelContextWindow('deepseek/deepseek-chat')).toBe(128_000);
    expect(inferModelContextWindow('deepseek-reasoner')).toBe(128_000);
  });

  it('uses 1M for GLM-5.2 (Z.ai / OpenRouter)', () => {
    expect(inferModelContextWindow('z-ai/glm-5.2')).toBe(1_000_000);
    expect(inferModelContextWindow('glm-5.2')).toBe(1_000_000);
    expect(inferModelContextWindow('glm-5.2[1m]')).toBe(1_000_000);
  });
});

describe('formatCompactTokenCount', () => {
  it('compacts thousands and millions', () => {
    expect(formatCompactTokenCount(0)).toBe('0');
    expect(formatCompactTokenCount(999)).toBe('999');
    expect(formatCompactTokenCount(1200)).toBe('1.2k');
    expect(formatCompactTokenCount(381458)).toBe('381k');
    expect(formatCompactTokenCount(1_000_000)).toBe('1M');
  });
});
