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
// (reload, direct link, a link from elsewhere), or navigating to a plan of a
// different engineer set while a leftover pointer from an earlier build is
// still around, both leave it either unset or stale. `needsRecovery` covers
// both: unset (`baselinePlanId === null`) and stale (points at a plan of a
// different engineer set than the one now open — GET /plan/{id}/compare
// rejects that pair with "Планы построены для разных наборов бригад", so
// using it as-is is never correct). This recovers a matching baseline from
// GET /plan (list_plans) instead, the same way it would have been set at
// build time.
function useRecoveredBaselinePlanId(
  mainPlanId: number | undefined,
  region: RegionCode | undefined,
  engineerSetId: number | undefined,
  needsRecovery: boolean
) {
  const setBaselinePlanId = useUiStore((s) => s.setBaselinePlanId);

  const plansQuery = useQuery({
    queryKey: queryKeys.plans(region ?? '', engineerSetId ?? null),
    queryFn: () => getPlans(region as RegionCode, engineerSetId),
    enabled: needsRecovery && mainPlanId !== undefined && region !== undefined && engineerSetId !== undefined
  });

  useEffect(() => {
    if (!needsRecovery || !plansQuery.data || mainPlanId === undefined) return;
    const recovered = pickBaselinePlanId(plansQuery.data, mainPlanId);
    if (recovered !== null) setBaselinePlanId(recovered);
  }, [needsRecovery, plansQuery.data, mainPlanId, setBaselinePlanId]);

  // True once the plan list has settled and still found nothing to compare
  // against — as opposed to "still loading", which looks the same to the
  // caller otherwise (both have `data === undefined`).
  const baselineUnavailable =
    needsRecovery && plansQuery.isSuccess && pickBaselinePlanId(plansQuery.data, mainPlanId ?? -1) === null;

  return { baselineUnavailable };
}

export function usePlanCompare(mainPlanId: number | undefined) {
  const baselinePlanId = useUiStore((s) => s.baselinePlanId);
  const main = usePlan(mainPlanId);
  const baseline = usePlan(baselinePlanId ?? undefined);

  // A pointer left over from a previously built/viewed plan can belong to a
  // different engineer set than the plan now open (e.g. the dispatcher built
  // a plan for the default set, then opened one for a generated set from the
  // plans list — nothing clears the pointer on that navigation). Comparing
  // across sets is meaningless and the backend rejects it, so treat it the
  // same as "no baseline yet" rather than sending the mismatched pair.
  const baselineMismatched =
    baselinePlanId !== null &&
    main.data !== undefined &&
    baseline.data !== undefined &&
    baseline.data.engineerSetId !== main.data.engineerSetId;

  const { baselineUnavailable } = useRecoveredBaselinePlanId(
    mainPlanId,
    main.data?.region,
    main.data?.engineerSetId,
    baselinePlanId === null || baselineMismatched
  );

  const query = useQuery({
    queryKey: queryKeys.planCompare(mainPlanId ?? -1, baselinePlanId ?? -1),
    queryFn: () => comparePlan(mainPlanId as number, baselinePlanId as number),
    enabled: !baselineMismatched && planCompareReady(mainPlanId, baselinePlanId, main.data?.status, baseline.data?.status)
  });

  return { ...query, baselineUnavailable };
}
