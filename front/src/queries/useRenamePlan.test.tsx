import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useRenamePlan } from './useRenamePlan';
import { queryKeys } from './keys';
import type { Plan, PlanSummary } from '@/types/domain';

const renamePlanMock = vi.fn();
vi.mock('@/api/endpoints', () => ({
  renamePlan: (...args: unknown[]) => renamePlanMock(...args)
}));

const summary: PlanSummary = {
  planId: 42,
  name: 'План №42',
  region: 'east',
  engineerSetId: 1,
  planDate: '2026-08-17',
  algorithm: 'or_tools',
  status: 'done',
  createdAt: '2026-08-17T09:00:00',
  parentPlanId: null,
  failedReason: null
};

function renderRename(queryClient: QueryClient) {
  return renderHook(() => useRenamePlan('east'), {
    wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  });
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('useRenamePlan', () => {
  it('writes the renamed summary into every cached plans-list page of the region, without refetching', async () => {
    const renamed: PlanSummary = { ...summary, name: 'Утренний обход' };
    renamePlanMock.mockResolvedValue(renamed);
    const queryClient = new QueryClient();
    queryClient.setQueryData(queryKeys.plans('east', null), [summary]);
    const { result } = renderRename(queryClient);

    result.current.mutate({ planId: 42, name: 'Утренний обход' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(queryKeys.plans('east', null))).toEqual([renamed]);
  });

  it('merges the new name into the cached single-plan entry, without refetching', async () => {
    const renamed: PlanSummary = { ...summary, name: 'Утренний обход' };
    renamePlanMock.mockResolvedValue(renamed);
    const queryClient = new QueryClient();
    const cachedPlan: Plan = {
      planId: 42,
      name: 'План №42',
      algorithm: 'or_tools',
      status: 'done',
      region: 'east',
      engineerSetId: 1,
      engineers: [],
      unassigned: [],
      metrics: {
        engineersUsed: 0,
        totalDistanceKm: 0,
        distanceByEngineer: {},
        assignedCount: 0,
        unassignedCount: 0,
        idleTimeByEngineerMin: {}
      }
    };
    queryClient.setQueryData(queryKeys.plan(42), cachedPlan);
    const { result } = renderRename(queryClient);

    result.current.mutate({ planId: 42, name: 'Утренний обход' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(queryKeys.plan(42))).toEqual({ ...cachedPlan, name: 'Утренний обход' });
  });

  it('leaves the single-plan cache untouched when that plan was never opened', async () => {
    const renamed: PlanSummary = { ...summary, name: 'Утренний обход' };
    renamePlanMock.mockResolvedValue(renamed);
    const queryClient = new QueryClient();
    const { result } = renderRename(queryClient);

    result.current.mutate({ planId: 42, name: 'Утренний обход' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(queryKeys.plan(42))).toBeUndefined();
  });
});
