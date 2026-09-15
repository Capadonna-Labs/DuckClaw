import { describe, expect, it, vi } from 'vitest';
import {
  applyLastTurnTokenDisplay,
  floorContextBreakdownAtBilledInput,
} from './adminChatPure';

describe('floorContextBreakdownAtBilledInput', () => {
  it('attributes residual to tools when billed prompt exceeds heuristic', () => {
    const out = floorContextBreakdownAtBilledInput(
      {
        system: 4300,
        messages: 8300,
        tools: 0,
        tool_results: 0,
        tool_schemas: 0,
        total: 12600,
      },
      42529
    );
    expect(out.total).toBe(42529);
    expect(out.tools).toBe(42529 - 12600);
    expect(out.messages).toBe(8300);
    expect(out.system).toBe(4300);
  });

  it('leaves breakdown unchanged when billed is lower', () => {
    const bd = {
      system: 100,
      messages: 200,
      tools: 300,
      total: 600,
    };
    expect(floorContextBreakdownAtBilledInput(bd, 100)).toEqual(bd);
  });
});

describe('applyLastTurnTokenDisplay', () => {
  it('floors occupancy at billed input when heuristic has no tools (old gateway)', () => {
    const setUsage = vi.fn();
    const setCtx = vi.fn();
    const setBd = vi.fn();
    applyLastTurnTokenDisplay(
      setUsage,
      setCtx,
      {
        usage_tokens: { input_tokens: 42529, output_tokens: 70, total_tokens: 42599 },
        context_token_breakdown: { system: 4300, messages: 8300, tools: 0, total: 12600 },
      },
      setBd
    );
    expect(setCtx).toHaveBeenCalledWith(42529);
    expect(setBd.mock.calls[0][0].total).toBe(42529);
    expect(setBd.mock.calls[0][0].tools).toBe(29929);
  });

  it('trusts gateway breakdown that already includes tools (no inflate from turn sum)', () => {
    const setUsage = vi.fn();
    const setCtx = vi.fn();
    const setBd = vi.fn();
    applyLastTurnTokenDisplay(
      setUsage,
      setCtx,
      {
        usage_tokens: { input_tokens: 82529, output_tokens: 120, total_tokens: 82649 },
        context_token_breakdown: {
          system: 4300,
          messages: 8300,
          tools: 29929,
          total: 42529,
        },
      },
      setBd
    );
    expect(setCtx).toHaveBeenCalledWith(42529);
    expect(setBd.mock.calls[0][0].total).toBe(42529);
  });
});
