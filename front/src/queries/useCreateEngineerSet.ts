import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEngineerSet } from '@/api/endpoints';
import { queryKeys } from './keys';
import type { EngineerSetCreateRequest } from '@/api/generated/schemas';
import type { RegionCode } from '@/types/domain';

export function useCreateEngineerSet(region: RegionCode) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: EngineerSetCreateRequest) => createEngineerSet(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.engineerSets(region) });
    }
  });
}
