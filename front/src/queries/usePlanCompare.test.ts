import { describe, expect, it } from 'vitest';
import { comparePlanMetrics } from './usePlanCompare';
import type { PlanMetrics } from '@/types/domain';

function metrics(engineersUsed: number, totalDistanceKm: number): PlanMetrics {
  return {
    engineersUsed,
    totalDistanceKm,
    distanceByEngineer: {},
    assignedCount: 0,
    unassignedCount: 0,
    idleTimeByEngineerMin: {}
  };
}

describe('comparePlanMetrics', () => {
  it('is undefined while either plan has no metrics yet (still running or failed)', () => {
    expect(comparePlanMetrics(undefined, metrics(9, 187.3))).toBeUndefined();
    expect(comparePlanMetrics(metrics(9, 187.3), undefined)).toBeUndefined();
  });

  it('computes the delta (main - baseline) for both mandatory metrics once both are done', () => {
    const compare = comparePlanMetrics(metrics(9, 187.3), metrics(13, 244.9));

    expect(compare).toEqual({
      engineersUsed: { main: 9, baseline: 13, delta: -4 },
      totalDistanceKm: { main: 187.3, baseline: 244.9, delta: expect.closeTo(-57.6, 5) }
    });
  });
});
