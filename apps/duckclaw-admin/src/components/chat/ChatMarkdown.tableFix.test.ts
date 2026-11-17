import { describe, expect, it } from 'vitest';
import { fixTableDelimiterRows } from './ChatMarkdown';

describe('fixTableDelimiterRows', () => {
  it('resizes a delimiter row with one column too many (MSFT reply, 16-nov)', () => {
    const t = '| A | B | C |\n|---|---:|---:|---:|\n| 1 | 2 | 3 |';
    expect(fixTableDelimiterRows(t).split('\n')[1]).toBe('|---|---:|---:|');
  });
  it('pads a short one and leaves good tables alone', () => {
    expect(fixTableDelimiterRows('| A | B |\n|---|').split('\n')[1]).toBe('|---|---|');
    const ok = '| A | B |\n|---|---|';
    expect(fixTableDelimiterRows(ok)).toBe(ok);
  });
});
