import { useMutation, useQueryClient } from '@tanstack/react-query';
import { replan } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { ReplanEvent } from '@/types/domain';

export function useReplan(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (event: ReplanEvent) => replan(planId, event),
    onSuccess: (newPlan) => {
      queryClient.setQueryData(queryKeys.plan(newPlan.planId), newPlan);
    }
  });
}
