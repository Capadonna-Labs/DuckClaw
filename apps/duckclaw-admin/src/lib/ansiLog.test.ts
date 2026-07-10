import { describe, expect, it } from 'vitest';
import { colorizePlainLogLine, stripAnsi } from './ansiLogParse';

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
});
