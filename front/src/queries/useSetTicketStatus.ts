import { useMutation, useQueryClient } from '@tanstack/react-query';
import { setTicketStatus } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { TicketStatus } from '@/types/domain';

export function useSetTicketStatus(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ticketId, status }: { ticketId: number; status: TicketStatus }) =>
      setTicketStatus(ticketId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.plan(planId) });
    }
  });
}
