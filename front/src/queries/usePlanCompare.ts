import { usePlan } from './usePlan';
import { useUiStore } from '@/store/useUiStore';
import type { PlanCompare } from '@/types/domain';

// Derives the FR-11/FR-12 comparison from the already-cached main + baseline
// plans instead of GET /plan/{id}/compare — see api/types.ts for why.
export function usePlanCompare(mainPlanId: number | undefined): PlanCompare | undefined {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const main = usePlan(mainPlanId);
  const baseline = usePlan(baselinePlanId ?? undefined);

  if (!main.data || !baseline.data) return undefined;

  return {
    engineersUsed: {
      main: main.data.metrics.engineersUsed,
      baseline: baseline.data.metrics.engineersUsed,
      delta: main.data.metrics.engineersUsed - baseline.data.metrics.engineersUsed
    },
    totalDistanceKm: {
      main: main.data.metrics.totalDistanceKm,
      baseline: baseline.data.metrics.totalDistanceKm,
      delta: main.data.metrics.totalDistanceKm - baseline.data.metrics.totalDistanceKm
    }
  };
}
