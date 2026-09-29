import { describe, expect, it } from 'vitest';
import { planCompareReady } from './usePlanCompare';

describe('planCompareReady', () => {
  it('is false while either plan is still running or failed', () => {
    expect(planCompareReady(42, 43, 'running', 'done')).toBe(false);
    expect(planCompareReady(42, 43, 'done', 'failed')).toBe(false);
  });

  it('is false with no baseline plan selected yet', () => {
    expect(planCompareReady(42, null, 'done', 'done')).toBe(false);
  });

  it('is true once both the main and baseline plans are done', () => {
    expect(planCompareReady(42, 43, 'done', 'done')).toBe(true);
  });
});
