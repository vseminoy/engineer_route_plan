import { useQuery } from '@tanstack/react-query';
import { getPlans } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function usePlans(region: RegionCode | null, engineerSetId: number | null = null) {
  return useQuery({
    queryKey: queryKeys.plans(region ?? '', engineerSetId),
    queryFn: () => getPlans(region as RegionCode, engineerSetId),
    enabled: region !== null
  });
}
