import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PlanScreen } from './PlanScreen';
import { useUiStore } from '@/store/useUiStore';
import type { Plan } from '@/types/domain';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// The map needs a real DOM/canvas layout jsdom doesn't provide; PlanScreen's
// own branching (running/failed/done) is what's under test here, not the map.
vi.mock('@/components/map/MapView', () => ({ MapView: () => <div data-testid="map-view" /> }));

vi.mock('@/queries/useEngineers', () => ({ useEngineers: () => ({ data: [], isError: false }) }));
vi.mock('@/queries/useTickets', () => ({ useTickets: () => ({ data: [], isError: false }) }));

const usePlanMock = vi.fn();
vi.mock('@/queries/usePlan', () => ({ usePlan: (...args: unknown[]) => usePlanMock(...args) }));

const buildPlanMock = vi.fn();
vi.mock('@/api/endpoints', () => ({ buildPlan: (...args: unknown[]) => buildPlanMock(...args) }));

function renderPlanScreen(planId = 42) {
  return render(
    <MemoryRouter initialEntries={[`/plan/${planId}`]}>
      <Routes>
        <Route path="/plan/:planId" element={<PlanScreen />} />
      </Routes>
    </MemoryRouter>
  );
}

function planQueryResult(data: Plan | undefined, overrides: Record<string, unknown> = {}) {
  return { isPending: data === undefined, isError: false, isFetching: false, data, ...overrides };
}

afterEach(() => {
  vi.clearAllMocks();
  useUiStore.setState({ selectedRegion: 'east' });
});

describe('PlanScreen — running/done/failed transitions', () => {
  it('shows the waiting message while the build is still running (polling handled by usePlan itself)', () => {
    usePlanMock.mockReturnValue(planQueryResult({ planId: 42, algorithm: 'or_tools', status: 'running' }));

    renderPlanScreen();

    expect(screen.getByText('Подождите, идёт расчёт…')).toBeInTheDocument();
    expect(screen.queryByTestId('map-view')).not.toBeInTheDocument();
  });

  it('renders the plan once the build is done', () => {
    usePlanMock.mockReturnValue(
      planQueryResult({
        planId: 42,
        algorithm: 'or_tools',
        status: 'done',
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
      })
    );

    renderPlanScreen();

    expect(screen.getByTestId('map-view')).toBeInTheDocument();
    expect(screen.getByText(/Диспетчер/)).toBeInTheDocument();
    expect(screen.queryByText('Подождите, идёт расчёт…')).not.toBeInTheDocument();
  });

  it('shows the failure reason and a rebuild button when the build failed, and rebuilds on click', async () => {
    usePlanMock.mockReturnValue(
      planQueryResult({ planId: 42, algorithm: 'or_tools', status: 'failed', failedReason: 'osrm_unavailable' })
    );
    buildPlanMock.mockResolvedValue({ planId: 99, algorithm: 'or_tools', status: 'running' });

    renderPlanScreen();

    expect(screen.getByText('Сервис маршрутов недоступен')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Построить заново' });

    await act(async () => fireEvent.click(button));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/plan/99'));
    expect(buildPlanMock).toHaveBeenCalledWith('east', expect.any(String), 'or_tools');
  });
});
