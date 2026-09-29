import { useQuery } from '@tanstack/react-query';
import { comparePlan } from '@/api/endpoints';
import { usePlan } from './usePlan';
import { useUiStore } from '@/store/useUiStore';
import { queryKeys } from './keys';
import type { PlanStatus } from '@/types/domain';

// GET /plan/{id}/compare requires both plans to already be status: 'done'
// (otherwise 400) — this is the gate `usePlanCompare` passes to `enabled`.
export function planCompareReady(
  mainPlanId: number | undefined,
  baselinePlanId: number | null,
  mainStatus: PlanStatus | undefined,
  baselineStatus: PlanStatus | undefined
): boolean {
  return mainPlanId !== undefined && baselinePlanId !== null && mainStatus === 'done' && baselineStatus === 'done';
}

export function usePlanCompare(mainPlanId: number | undefined) {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const main = usePlan(mainPlanId);
  const baseline = usePlan(baselinePlanId ?? undefined);

  return useQuery({
    queryKey: queryKeys.planCompare(mainPlanId ?? -1, baselinePlanId ?? -1),
    queryFn: () => comparePlan(mainPlanId as number, baselinePlanId as number),
    enabled: planCompareReady(mainPlanId, baselinePlanId, main.data?.status, baseline.data?.status)
  });
}
