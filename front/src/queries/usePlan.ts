import { useQuery } from '@tanstack/react-query';
import { getPlan } from '@/api/endpoints';
import { queryKeys } from './keys';

export function usePlan(planId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.plan(planId ?? -1),
    queryFn: () => getPlan(planId as number),
    enabled: planId !== undefined
  });
}
