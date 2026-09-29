import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteEngineerSet } from '@/api/endpoints';
import { useUiStore } from '@/store/useUiStore';
import { queryKeys } from './keys';
import type { RegionCode } from '@/types/domain';

export function useDeleteEngineerSet(region: RegionCode) {
  const queryClient = useQueryClient();
  const selectedEngineerSetId = useUiStore((s) => s.selectedEngineerSetId);
  const setSelectedEngineerSetId = useUiStore((s) => s.setSelectedEngineerSetId);

  return useMutation({
    mutationFn: (engineerSetId: number) => deleteEngineerSet(engineerSetId),
    onSuccess: (_data, engineerSetId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.engineerSets(region) });
      queryClient.invalidateQueries({ queryKey: queryKeys.engineers(region) });
      if (selectedEngineerSetId === engineerSetId) setSelectedEngineerSetId(null);
    }
  });
}
