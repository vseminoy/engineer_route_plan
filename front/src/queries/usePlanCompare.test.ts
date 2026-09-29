import { describe, expect, it } from 'vitest';
import { pickBaselinePlanId, planCompareReady } from './usePlanCompare';
import type { PlanSummary } from '@/types/domain';

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

function _summary(overrides: Partial<PlanSummary> & { planId: number }): PlanSummary {
  return {
    region: 'east',
    engineerSetId: 70,
    planDate: '2026-09-01',
    algorithm: 'or_tools',
    status: 'done',
    createdAt: '2026-09-01T09:00:00',
    parentPlanId: null,
    failedReason: null,
    ...overrides
  };
}

describe('pickBaselinePlanId', () => {
  it('finds the done baseline_fcfs plan of the same plan_date', () => {
    const plans = [
      _summary({ planId: 1, algorithm: 'or_tools', createdAt: '2026-09-01T09:00:05' }),
      _summary({ planId: 2, algorithm: 'baseline_fcfs', createdAt: '2026-09-01T09:00:00' })
    ];
    expect(pickBaselinePlanId(plans, 1)).toBe(2);
  });

  it('picks the baseline created closest to the main plan when two builds share a plan_date', () => {
    const plans = [
      _summary({ planId: 1, algorithm: 'or_tools', createdAt: '2026-09-01T12:00:00' }),
      _summary({ planId: 2, algorithm: 'baseline_fcfs', createdAt: '2026-09-01T09:00:00' }),
      _summary({ planId: 3, algorithm: 'baseline_fcfs', createdAt: '2026-09-01T11:59:00' })
    ];
    expect(pickBaselinePlanId(plans, 1)).toBe(3);
  });

  it('ignores a baseline of a different plan_date, or one that is not done', () => {
    const plans = [
      _summary({ planId: 1, algorithm: 'or_tools', planDate: '2026-09-02' }),
      _summary({ planId: 2, algorithm: 'baseline_fcfs', planDate: '2026-09-01' }),
      _summary({ planId: 3, algorithm: 'baseline_fcfs', planDate: '2026-09-02', status: 'running' })
    ];
    expect(pickBaselinePlanId(plans, 1)).toBeNull();
  });

  it('returns null when the main plan itself is not in the list', () => {
    expect(pickBaselinePlanId([], 1)).toBeNull();
  });
});
