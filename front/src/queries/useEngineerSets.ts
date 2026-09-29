import { useQuery } from '@tanstack/react-query';
import { getEngineerSets } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function useEngineerSets(region: RegionCode | null) {
  return useQuery({
    queryKey: queryKeys.engineerSets(region ?? ''),
    queryFn: () => getEngineerSets(region as RegionCode),
    enabled: region !== null
  });
}
