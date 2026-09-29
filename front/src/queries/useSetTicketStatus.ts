import { useMutation, useQueryClient } from '@tanstack/react-query';
import { setTicketStatus } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode, TicketStatus, TicketSummary } from '@/types/domain';

// The response is the ticket itself, not the plan — the operation leaves
// built plans unchanged (assignment/route data live there, not the ticket's
// own status), so the ['tickets', region] entry is patched directly instead
// of refetching; ['plan', planId] is still invalidated per the region/plan
// cache contract shared with the rest of the screen.
export function useSetTicketStatus(planId: number, region: RegionCode | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ticketId, status }: { ticketId: number; status: TicketStatus }) =>
      setTicketStatus(ticketId, status),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.plan(planId) });
      if (region === null) return;
      queryClient.setQueryData<TicketSummary[]>(queryKeys.tickets(region), (tickets) =>
        tickets?.map((t) => (t.ticketId === updated.ticketId ? updated : t))
      );
    }
  });
}
