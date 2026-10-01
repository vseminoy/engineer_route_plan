import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PlanRenameModal } from './PlanRenameModal';
import { ApiError } from '@/api/client';
import type { PlanSummary } from '@/types/domain';

const renamePlanMock = vi.fn();
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>();
  return { ...actual, renamePlan: (...args: unknown[]) => renamePlanMock(...args) };
});

const plan: PlanSummary = {
  planId: 42,
  name: 'План №42',
  region: 'east',
  engineerSetId: 70,
  planDate: '2026-08-17',
  algorithm: 'or_tools',
  status: 'done',
  createdAt: '2026-08-17T09:00:00',
  parentPlanId: null,
  failedReason: null
};

function renderModal(onRenamed = vi.fn()) {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <PlanRenameModal region="east" plan={plan} onRenamed={onRenamed} onCancel={vi.fn()} />
    </QueryClientProvider>
  );
  return { onRenamed };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('PlanRenameModal', () => {
  it('shows the plan’s current name pre-filled in the input', () => {
    renderModal();

    expect(screen.getByRole('textbox')).toHaveValue('План №42');
  });

  it('rejects an empty name (after trimming) before sending the request', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать' }));

    expect(screen.getByText('Too small: expected string to have >=1 characters')).toBeInTheDocument();
    expect(renamePlanMock).not.toHaveBeenCalled();
  });

  it('rejects a name longer than 100 characters before sending the request', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'a'.repeat(101) } });

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать' }));

    expect(screen.getByText('Too big: expected string to have <=100 characters')).toBeInTheDocument();
    expect(renamePlanMock).not.toHaveBeenCalled();
  });

  it('renames the plan and reports the new summary to the parent', async () => {
    const renamed: PlanSummary = { ...plan, name: 'Утренний обход' };
    renamePlanMock.mockResolvedValue(renamed);
    const { onRenamed } = renderModal();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  Утренний обход  ' } });

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать' }));

    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith(renamed));
    expect(renamePlanMock).toHaveBeenCalledWith(42, 'Утренний обход');
  });

  it('shows the field error from the 400 response when the server rejects it', async () => {
    renamePlanMock.mockRejectedValue(
      new ApiError(400, 'req-1', { fields: [{ name: 'name', message: 'Название не может быть пустым' }] })
    );
    renderModal();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Новое название' } });

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать' }));

    expect(await screen.findByText('Название не может быть пустым')).toBeInTheDocument();
  });

  it('shows the dictionary message when the plan is already gone (404)', async () => {
    renamePlanMock.mockRejectedValue(new ApiError(404, 'req-2'));
    renderModal();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Новое название' } });

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать' }));

    expect(await screen.findByText('План уже удалён')).toBeInTheDocument();
  });
});
