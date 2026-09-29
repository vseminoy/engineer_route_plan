import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { comparePlan, getPlans } from '@/api/endpoints';
import { usePlan } from './usePlan';
import { useUiStore } from '@/store/useUiStore';
import { queryKeys } from './keys';
import type { PlanStatus, PlanSummary, RegionCode } from '@/types/domain';

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

// The baseline_fcfs plan `useBuildPlan` built alongside `mainPlanId`, same
// plan_date, closest created_at (two builds can share a plan_date). `null`
// when the plan list hasn't loaded yet, or genuinely has no match.
export function pickBaselinePlanId(plans: PlanSummary[], mainPlanId: number): number | null {
  const main = plans.find((p) => p.planId === mainPlanId);
  if (!main) return null;
  const candidates = plans.filter(
    (p) => p.algorithm === 'baseline_fcfs' && p.status === 'done' && p.planDate === main.planDate
  );
  if (candidates.length === 0) return null;
  const mainCreatedAt = new Date(main.createdAt).getTime();
  return candidates.reduce((best, c) =>
    Math.abs(new Date(c.createdAt).getTime() - mainCreatedAt) < Math.abs(new Date(best.createdAt).getTime() - mainCreatedAt)
      ? c
      : best
  ).planId;
}

// `baselinePlanId` (useUiStore) is a session-only pointer, set only right
// after `useBuildPlan` succeeds — opening a plan straight from its URL
// (reload, direct link, a link from elsewhere) never populates it, which
// otherwise leaves the Metrics tab stuck on "Считаем сравнение с baseline…"
// forever, since the compare query stays disabled with no baseline id to
// query with. This recovers it from GET /plan (list_plans) instead, once,
// the same way it would have been set at build time.
function useRecoveredBaselinePlanId(
  mainPlanId: number | undefined,
  region: RegionCode | undefined,
  engineerSetId: number | undefined
) {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const setBaselinePlanId = useUiStore((s) => s.setBaselinePlanId);

  const plansQuery = useQuery({
    queryKey: queryKeys.plans(region ?? '', engineerSetId ?? null),
    queryFn: () => getPlans(region as RegionCode, engineerSetId),
    enabled: baselinePlanId === null && mainPlanId !== undefined && region !== undefined && engineerSetId !== undefined
  });

  useEffect(() => {
    if (baselinePlanId !== null || !plansQuery.data || mainPlanId === undefined) return;
    const recovered = pickBaselinePlanId(plansQuery.data, mainPlanId);
    if (recovered !== null) setBaselinePlanId(recovered);
  }, [baselinePlanId, plansQuery.data, mainPlanId, setBaselinePlanId]);

  // True once the plan list has settled and still found nothing to compare
  // against — as opposed to "still loading", which looks the same to the
  // caller otherwise (both have `data === undefined`).
  const baselineUnavailable =
    baselinePlanId === null && plansQuery.isSuccess && pickBaselinePlanId(plansQuery.data, mainPlanId ?? -1) === null;

  return { baselineUnavailable };
}

export function usePlanCompare(mainPlanId: number | undefined) {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const main = usePlan(mainPlanId);
  const { baselineUnavailable } = useRecoveredBaselinePlanId(mainPlanId, main.data?.region, main.data?.engineerSetId);
  const baseline = usePlan(baselinePlanId ?? undefined);

  const query = useQuery({
    queryKey: queryKeys.planCompare(mainPlanId ?? -1, baselinePlanId ?? -1),
    queryFn: () => comparePlan(mainPlanId as number, baselinePlanId as number),
    enabled: planCompareReady(mainPlanId, baselinePlanId, main.data?.status, baseline.data?.status)
  });

  return { ...query, baselineUnavailable };
}
