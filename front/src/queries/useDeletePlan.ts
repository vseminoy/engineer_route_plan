import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deletePlan } from '@/api/endpoints';
import type { RegionCode } from '@/types/domain';

export function useDeletePlan(region: RegionCode) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (planId: number) => deletePlan(planId),
    onSuccess: () => {
      // No engineerSetId — matches every set's cached list for the region,
      // same convention as invalidating ['engineers', regionCode].
      queryClient.invalidateQueries({ queryKey: ['plans', region] });
    }
  });
}
