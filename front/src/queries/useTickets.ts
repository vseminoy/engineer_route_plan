import { useQuery } from '@tanstack/react-query';
import { getTickets } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function useTickets(region: RegionCode | null) {
  return useQuery({
    queryKey: queryKeys.tickets(region ?? ''),
    queryFn: () => getTickets(region as RegionCode),
    enabled: region !== null
  });
}
