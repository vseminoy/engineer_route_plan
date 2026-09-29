import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EngineerSetCreateForm } from './EngineerSetCreateForm';
import { ApiError } from '@/api/client';
import type { EngineerSet } from '@/types/domain';

const createEngineerSetMock = vi.fn();
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>();
  return { ...actual, createEngineerSet: (...args: unknown[]) => createEngineerSetMock(...args) };
});

function renderForm(onCreated = vi.fn()) {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <EngineerSetCreateForm region="east" onCreated={onCreated} onCancel={vi.fn()} />
    </QueryClientProvider>
  );
  return { onCreated };
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText('Название'), { target: { value: '13 бригад' } });
  fireEvent.change(screen.getByLabelText('Число бригад'), { target: { value: '13' } });
  fireEvent.change(screen.getByLabelText('Доля утренней смены'), { target: { value: '0.6' } });
  fireEvent.change(screen.getByLabelText('Доля вечерней смены'), { target: { value: '0.4' } });
  fireEvent.change(screen.getByLabelText('Зерно генератора (seed)'), { target: { value: 'demo-13' } });
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('EngineerSetCreateForm', () => {
  it('rejects an empty name and seed before sending the request', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Число бригад'), { target: { value: '13' } });

    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    expect(screen.getAllByText('Too small: expected string to have >=1 characters').length).toBeGreaterThan(0);
    expect(createEngineerSetMock).not.toHaveBeenCalled();
  });

  it('rejects a shift share out of the 0–1 range before sending the request', () => {
    renderForm();
    fillValidForm();
    fireEvent.change(screen.getByLabelText('Доля вечерней смены'), { target: { value: '1.5' } });

    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    expect(screen.getByText('Too big: expected number to be <=1')).toBeInTheDocument();
    expect(createEngineerSetMock).not.toHaveBeenCalled();
  });

  it('sends a valid form and reports the created set to the parent', async () => {
    const created: EngineerSet = {
      id: 7,
      name: '13 бригад',
      kind: 'generated',
      engineers: 13,
      morningShare: 0.6,
      eveningShare: 0.4,
      seed: 'demo-13',
      description: '13 бригад, 60%/40%, seed demo-13'
    };
    createEngineerSetMock.mockResolvedValue(created);
    const { onCreated } = renderForm();
    fillValidForm();

    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    expect(createEngineerSetMock).toHaveBeenCalledWith({
      region: 'east',
      name: '13 бригад',
      engineers: 13,
      morning_share: 0.6,
      evening_share: 0.4,
      seed: 'demo-13'
    });
  });

  it('shows the dictionary message on a duplicate name (409)', async () => {
    createEngineerSetMock.mockRejectedValue(new ApiError(409, 'req-1'));
    renderForm();
    fillValidForm();

    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    expect(await screen.findByText('Набор с таким названием уже есть в регионе')).toBeInTheDocument();
  });
});
