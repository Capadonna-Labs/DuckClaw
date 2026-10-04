import { describe, expect, it } from 'vitest';
import { workersTooltipLabel } from './workersTooltipLabel';

describe('workersTooltipLabel', () => {
  it('reports empty state', () => {
    expect(workersTooltipLabel([])).toBe('Sin workers activos');
  });

  it('joins active worker ids', () => {
    expect(workersTooltipLabel(['Worker-B', 'worker-a'])).toBe(
      'Worker-B, worker-a'
    );
  });
});
