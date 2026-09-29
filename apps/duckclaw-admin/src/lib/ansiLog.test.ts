import { describe, expect, it } from 'vitest';
import { colorizePlainLogLine, hasAnsiCodes, stripAnsi } from './ansiLogParse';

describe('ansiLogParse', () => {
  it('strips ANSI escape codes', () => {
    expect(stripAnsi('\x1b[31merror\x1b[0m')).toBe('error');
  });

  it('colorizes plain log lines for light and dark themes', () => {
    expect(colorizePlainLogLine('ERROR: boom').className).toBe('text-red-700 dark:text-red-400');
    expect(colorizePlainLogLine('WARN: slow').className).toBe('text-amber-700 dark:text-amber-300');
    expect(colorizePlainLogLine('0|Gateway | info').className).toBe(
      'text-emerald-700 dark:text-emerald-300',
    );
  });

  it('paints tool-usage and plan lines yellow', () => {
    expect(
      colorizePlainLogLine('2026-09-29 16:54:47 | [default:manager] | unknown | [TOOL] inspect_custom_report -> OK (⏱️ 231ms)')
        .className,
    ).toBe('text-yellow-700 dark:text-yellow-300');
    expect(
      colorizePlainLogLine(
        '2026-09-29 16:20:27 | [user:x] | tool_usage: worker=quant_analyst | tool=read_sql | phase=done | elapsed_ms=452',
      ).className,
    ).toBe('text-yellow-700 dark:text-yellow-300');
    expect(
      colorizePlainLogLine("[quant_analyst] tool=read_sql | result_len=595 | preview='...'").className,
    ).toBe('text-yellow-700 dark:text-yellow-300');
    expect(
      colorizePlainLogLine(
        '2026-09-29 17:13:41 | [user:x] | [PLAN] "Revisar notificaciones Android pendientes" | tasks: [...]',
      ).className,
    ).toBe('text-yellow-700 dark:text-yellow-300');
  });

  it('paints harness_metric lines green even when the payload has "denied"/"failures" fields', () => {
    // Regression: {'risk_denied': 0, 'failures': 0} used to trip the red error
    // regex via plain substring matching ("denied", "failure") before this
    // line type had its own check — harness_metric must win first.
    expect(
      colorizePlainLogLine(
        "[quant_analyst] harness_metric {'approval_mode': 'suggest', 'circuit_blocks': 0, 'risk_denied': 0, 'failures': 0, 'truncated_results': 0, 'fail_counts': {}}",
      ).className,
    ).toBe('text-emerald-700 dark:text-emerald-300');
  });

  it('regression: a real PM2 stream mixes ANSI and plain lines — each line must be judged on its own, not the whole buffer', () => {
    // Same shape as a real stream: a colored PM2 banner line, then a plain
    // Python traceback with zero ANSI codes (exactly what silently stopped
    // rendering red — the old code checked hasAnsiCodes() once for the whole
    // buffer, and one ANSI line anywhere turned off colorizePlainLogLine for
    // every other line, including this one).
    const banner = '\x1b[32m[PM2] App launched\x1b[0m';
    const traceback = "zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key US/Eastern'";
    const buffer = `${banner}\n${traceback}`;

    expect(hasAnsiCodes(banner)).toBe(true);
    expect(hasAnsiCodes(traceback)).toBe(false);
    // the bug: checking the whole buffer at once hides the plain line's own status
    expect(hasAnsiCodes(buffer)).toBe(true);

    // what the fixed ansiTextToSpans now does: decide per split('\n') line
    const perLineVerdicts = buffer.split('\n').map(hasAnsiCodes);
    expect(perLineVerdicts).toEqual([true, false]);
    expect(colorizePlainLogLine(traceback).className).toBe('text-red-700 dark:text-red-400');
  });
});
