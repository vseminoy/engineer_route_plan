import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EngineerSetDeleteConfirm } from './EngineerSetDeleteConfirm';
import { ApiError } from '@/api/client';
import type { EngineerSet } from '@/types/domain';

const deleteEngineerSetMock = vi.fn();
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>();
  return { ...actual, deleteEngineerSet: (...args: unknown[]) => deleteEngineerSetMock(...args) };
});

const generatedSet: EngineerSet = {
  id: 7,
  name: '13 бригад',
  kind: 'generated',
  engineers: 13,
  morningShare: 0.6,
  eveningShare: 0.4,
  seed: 'demo-13',
  description: '13 бригад, 60%/40%, seed demo-13'
};

function renderConfirm(onDeleted = vi.fn()) {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <EngineerSetDeleteConfirm region="east" engineerSet={generatedSet} onDeleted={onDeleted} onCancel={vi.fn()} />
    </QueryClientProvider>
  );
  return { onDeleted };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('EngineerSetDeleteConfirm', () => {
  it('warns that the set’s plans are deleted with it', () => {
    renderConfirm();

    expect(screen.getByText('Планы этого набора тоже будут удалены.')).toBeInTheDocument();
  });

  it('deletes the set and reports it to the parent', async () => {
    deleteEngineerSetMock.mockResolvedValue(undefined);
    const { onDeleted } = renderConfirm();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(deleteEngineerSetMock).toHaveBeenCalledWith(7);
  });

  it('shows the dictionary message when the set is already gone (404)', async () => {
    deleteEngineerSetMock.mockRejectedValue(new ApiError(404, 'req-1'));
    renderConfirm();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(await screen.findByText('Набор уже удалён')).toBeInTheDocument();
  });
});
