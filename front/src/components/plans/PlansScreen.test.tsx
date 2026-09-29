import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PlansScreen } from './PlansScreen';
import { useUiStore } from '@/store/useUiStore';
import type { PlanSummary } from '@/types/domain';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/queries/useRegions', () => ({
  useRegions: () => ({ data: [{ code: 'east', name: 'Восток' }] })
}));

const getPlansMock = vi.fn();
const deletePlanMock = vi.fn();
vi.mock('@/api/endpoints', () => ({
  getPlans: (...args: unknown[]) => getPlansMock(...args),
  deletePlan: (...args: unknown[]) => deletePlanMock(...args)
}));

const DONE_PLAN: PlanSummary = {
  planId: 42,
  region: 'east',
  engineerSetId: 70,
  planDate: '2026-08-17',
  algorithm: 'or_tools',
  status: 'done',
  createdAt: '2026-08-17T09:05:00',
  parentPlanId: null,
  failedReason: null
};

function renderScreen() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlansScreen />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.clearAllMocks();
  useUiStore.setState({ selectedRegion: null, selectedEngineerSetId: null });
});

describe('PlansScreen', () => {
  it('prompts for a region before showing any plans', () => {
    renderScreen();

    expect(screen.getByText('Выберите регион, чтобы увидеть его планы.')).toBeInTheDocument();
    expect(getPlansMock).not.toHaveBeenCalled();
  });

  it('lists the region’s plans once loaded', async () => {
    getPlansMock.mockResolvedValue([DONE_PLAN]);
    renderScreen();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'east' } });

    expect(await screen.findByText('План №42')).toBeInTheDocument();
    expect(screen.getByText('Готов')).toBeInTheDocument();
    expect(getPlansMock).toHaveBeenCalledWith('east', null);
  });

  it('shows an empty-state message when the region has no plans', async () => {
    getPlansMock.mockResolvedValue([]);
    renderScreen();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'east' } });

    expect(await screen.findByText('У этого региона ещё нет построенных планов.')).toBeInTheDocument();
  });

  it('opens the plan on a row click', async () => {
    getPlansMock.mockResolvedValue([DONE_PLAN]);
    renderScreen();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'east' } });

    fireEvent.click(await screen.findByText('План №42'));

    expect(mockNavigate).toHaveBeenCalledWith('/plan/42');
  });

  it('opens the delete confirmation without navigating when its button is clicked', async () => {
    getPlansMock.mockResolvedValue([DONE_PLAN]);
    renderScreen();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'east' } });
    await screen.findByText('План №42');

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(screen.getByText('Удалить план №42?')).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('removes the deleted plan from the list', async () => {
    getPlansMock.mockResolvedValueOnce([DONE_PLAN]).mockResolvedValueOnce([]);
    deletePlanMock.mockResolvedValue(undefined);
    renderScreen();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'east' } });
    await screen.findByText('План №42');

    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Удалить' }));

    await waitFor(() => expect(screen.queryByText('План №42')).not.toBeInTheDocument());
    expect(deletePlanMock).toHaveBeenCalledWith(42);
  });
});
