import { usePlan } from './usePlan';
import { useUiStore } from '@/store/useUiStore';
import type { PlanCompare, PlanMetrics } from '@/types/domain';

// The mandatory comparison (engineers used, total distance): undefined until
// both plans have finished and have metrics — a plan still running or failed
// has none.
export function comparePlanMetrics(
  main: PlanMetrics | undefined,
  baseline: PlanMetrics | undefined
): PlanCompare | undefined {
  if (!main || !baseline) return undefined;

  return {
    engineersUsed: {
      main: main.engineersUsed,
      baseline: baseline.engineersUsed,
      delta: main.engineersUsed - baseline.engineersUsed
    },
    totalDistanceKm: {
      main: main.totalDistanceKm,
      baseline: baseline.totalDistanceKm,
      delta: main.totalDistanceKm - baseline.totalDistanceKm
    }
  };
}

// Derives the comparison from the already-cached main + baseline plans
// instead of GET /plan/{id}/compare — see api/types.ts for why.
export function usePlanCompare(mainPlanId: number | undefined): PlanCompare | undefined {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const main = usePlan(mainPlanId);
  const baseline = usePlan(baselinePlanId ?? undefined);

  return comparePlanMetrics(main.data?.metrics, baseline.data?.metrics);
}
