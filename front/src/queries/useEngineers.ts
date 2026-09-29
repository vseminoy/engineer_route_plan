import { useQuery } from '@tanstack/react-query';
import { getEngineers } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function useEngineers(region: RegionCode | null, engineerSetId: number | null = null) {
  return useQuery({
    queryKey: queryKeys.engineers(region ?? '', engineerSetId),
    queryFn: () => getEngineers(region as RegionCode, engineerSetId),
    enabled: region !== null
  });
}
