import { useQuery } from '@tanstack/react-query';
import { getPlan } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { PlanStatus } from '@/types/domain';

// POST /plan/build queues the build and answers before it's done; this polls
// GET /plan/{id} every 2s while status is 'running' and stops on its own the
// moment it isn't.
export const RUNNING_POLL_INTERVAL_MS = 2000;

export function planRefetchInterval(status: PlanStatus | undefined): number | false {
  return status === 'running' ? RUNNING_POLL_INTERVAL_MS : false;
}

export function usePlan(planId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.plan(planId ?? -1),
    queryFn: () => getPlan(planId as number),
    enabled: planId !== undefined,
    refetchInterval: (query) => planRefetchInterval(query.state.data?.status)
  });
}
