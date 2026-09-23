import { useMutation, useQueryClient } from '@tanstack/react-query';
import { buildPlan } from '@/api/endpoints';
import { useUiStore } from '@/store/useUiStore';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

// Builds the main (or_tools) plan the dispatcher will work with, plus a
// baseline_fcfs plan for the same region/date so the Metrics tab has
// something to compare against (05_spec_backend.md §4.2, FR-11/FR-12).
// Both responses are seeded straight into the TanStack Query cache — no
// separate compare-endpoint round trip needed.
export function useBuildPlan() {
  const queryClient = useQueryClient();
  const setBaselinePlanId = useUiStore((s) => s.setBaselinePlanId);

  return useMutation({
    mutationFn: async ({ region, planDate }: { region: RegionCode; planDate: string }) => {
      const [main, baseline] = await Promise.all([
        buildPlan(region, planDate, 'or_tools'),
        buildPlan(region, planDate, 'baseline_fcfs')
      ]);
      return { main, baseline };
    },
    onSuccess: ({ main, baseline }) => {
      queryClient.setQueryData(queryKeys.plan(main.planId), main);
      queryClient.setQueryData(queryKeys.plan(baseline.planId), baseline);
      setBaselinePlanId(baseline.planId);
    }
  });
}
