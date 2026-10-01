import { useMutation, useQueryClient } from '@tanstack/react-query';
import { renamePlan } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { Plan, PlanSummary, RegionCode } from '@/types/domain';

export function useRenamePlan(region: RegionCode) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ planId, name }: { planId: number; name: string }) => renamePlan(planId, name),
    onSuccess: (summary) => {
      // Written straight from the response, not invalidated — the list is already
      // in hand and a refetch would be a round trip for data this call just returned.
      queryClient.setQueriesData<PlanSummary[]>({ queryKey: ['plans', region] }, (plans) =>
        plans?.map((p) => (p.planId === summary.planId ? summary : p))
      );
      queryClient.setQueryData<Plan>(queryKeys.plan(summary.planId), (plan) =>
        plan ? { ...plan, name: summary.name } : plan
      );
    }
  });
}
