import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PlanDeleteConfirm } from './PlanDeleteConfirm';
import { ApiError } from '@/api/client';
import type { PlanSummary } from '@/types/domain';

const deletePlanMock = vi.fn();
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>();
  return { ...actual, deletePlan: (...args: unknown[]) => deletePlanMock(...args) };
});

const plan: PlanSummary = {
  planId: 42,
  region: 'east',
  engineerSetId: 70,
  planDate: '2026-08-17',
  algorithm: 'or_tools',
  status: 'done',
  createdAt: '2026-08-17T09:00:00',
  parentPlanId: null,
  failedReason: null
};

function renderConfirm(onDeleted = vi.fn()) {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <PlanDeleteConfirm region="east" plan={plan} onDeleted={onDeleted} onCancel={vi.fn()} />
    </QueryClientProvider>
  );
  return { onDeleted };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('PlanDeleteConfirm', () => {
  it('warns that replans made from this plan are deleted with it', () => {
    renderConfirm();

    expect(
      screen.getByText('Все перепланирования, сделанные от этого плана, тоже будут удалены.')
    ).toBeInTheDocument();
  });

  it('deletes the plan and reports it to the parent', async () => {
    deletePlanMock.mockResolvedValue(undefined);
    const { onDeleted } = renderConfirm();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(deletePlanMock).toHaveBeenCalledWith(42);
  });

  it('shows the dictionary message when the plan is already gone (404)', async () => {
    deletePlanMock.mockRejectedValue(new ApiError(404, 'req-1'));
    renderConfirm();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(await screen.findByText('План уже удалён')).toBeInTheDocument();
  });

  it('shows the dictionary message when the plan is still running (409)', async () => {
    deletePlanMock.mockRejectedValue(new ApiError(409, 'req-2'));
    renderConfirm();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(await screen.findByText('План ещё строится — подождите и попробуйте снова')).toBeInTheDocument();
  });
});
