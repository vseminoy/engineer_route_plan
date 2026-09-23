import { useQuery } from '@tanstack/react-query';
import { getEngineers } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function useEngineers(region: RegionCode | null) {
  return useQuery({
    queryKey: queryKeys.engineers(region ?? ''),
    queryFn: () => getEngineers(region as RegionCode),
    enabled: region !== null
  });
}
