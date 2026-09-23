import { useQuery } from '@tanstack/react-query';
import { getRegions } from '@/api/endpoints';
import { queryKeys } from './keys';

export function useRegions() {
  return useQuery({ queryKey: queryKeys.regions(), queryFn: getRegions });
}
