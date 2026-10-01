import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { usePlanCompare } from './usePlanCompare';
import { useUiStore } from '@/store/useUiStore';
import type { Plan, PlanSummary } from '@/types/domain';

const getPlanMock = vi.fn();
const getPlansMock = vi.fn();
const comparePlanMock = vi.fn();
vi.mock('@/api/endpoints', () => ({
  getPlan: (...args: unknown[]) => getPlanMock(...args),
  getPlans: (...args: unknown[]) => getPlansMock(...args),
  comparePlan: (...args: unknown[]) => comparePlanMock(...args)
}));

function plan(overrides: Partial<Plan> & { planId: number; engineerSetId: number }): Plan {
  return {
    name: 'План №1',
    algorithm: 'or_tools',
    status: 'done',
    region: 'east',
    ...overrides
  };
}

function summary(overrides: Partial<PlanSummary> & { planId: number; engineerSetId: number }): PlanSummary {
  return {
    name: 'План №1',
    region: 'east',
    planDate: '2026-09-01',
    algorithm: 'baseline_fcfs',
    status: 'done',
    createdAt: '2026-09-01T09:00:00',
    parentPlanId: null,
    failedReason: null,
    ...overrides
  };
}

function renderCompare(mainPlanId: number) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => usePlanCompare(mainPlanId), {
    wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  });
}

afterEach(() => {
  vi.clearAllMocks();
  useUiStore.setState({ baselinePlanId: null });
});

describe('usePlanCompare — stale baseline pointer from a different engineer set', () => {
  it('never sends the mismatched pair to compare, and recovers a same-set baseline instead', async () => {
    // Main plan is for engineer set 4; the session's leftover baseline
    // pointer (from an earlier build against a different set) is for set 7 —
    // exactly the "id=4 build" scenario that used to hit "Планы построены
    // для разных наборов бригад".
    getPlanMock.mockImplementation((planId: number) => {
      if (planId === 100) return Promise.resolve(plan({ planId: 100, engineerSetId: 4 }));
      if (planId === 50) return Promise.resolve(plan({ planId: 50, engineerSetId: 7, algorithm: 'baseline_fcfs' }));
      throw new Error(`unexpected planId ${planId}`);
    });
    getPlansMock.mockResolvedValue([
      summary({ planId: 100, engineerSetId: 4, algorithm: 'or_tools', createdAt: '2026-09-01T09:00:05' }),
      summary({ planId: 101, engineerSetId: 4, createdAt: '2026-09-01T09:00:00' })
    ]);
    comparePlanMock.mockResolvedValue({
      engineersUsed: { main: 1, baseline: 1, delta: 0 },
      totalDistanceKm: { main: 1, baseline: 1, delta: 0 },
      unassignedCount: { main: 0, baseline: 0, delta: 0 }
    });

    useUiStore.setState({ baselinePlanId: 50 });

    renderCompare(100);

    await waitFor(() => expect(useUiStore.getState().baselinePlanId).toBe(101));
    expect(comparePlanMock).not.toHaveBeenCalledWith(100, 50);
  });
});
