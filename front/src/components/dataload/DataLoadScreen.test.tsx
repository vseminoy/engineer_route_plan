import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DataLoadScreen } from './DataLoadScreen';
import { useUiStore } from '@/store/useUiStore';
import { ApiError } from '@/api/client';

vi.mock('@/queries/useRegions', () => ({
  useRegions: () => ({ data: [{ code: 'east', name: 'Восток' }] })
}));

const loadDemoDatasetMock = vi.fn();
const buildPlanMock = vi.fn();
vi.mock('@/api/endpoints', () => ({
  loadDemoDataset: (...args: unknown[]) => loadDemoDatasetMock(...args),
  uploadDataset: vi.fn(),
  buildPlan: (...args: unknown[]) => buildPlanMock(...args),
  getEngineerSets: vi.fn().mockResolvedValue([])
}));

function renderScreen() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DataLoadScreen />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.clearAllMocks();
  useUiStore.setState({ selectedRegion: null });
});

describe('DataLoadScreen — POST /plan/build failing before it even queues', () => {
  it('shows a full-screen retry notice on a 503 from the build that follows a clean demo load', async () => {
    loadDemoDatasetMock.mockResolvedValue({
      region: 'east',
      engineersCount: 12,
      ticketsCount: 40,
      rowsTotal: 40,
      rowsSkipped: 0,
      invalidRows: []
    });
    buildPlanMock.mockRejectedValue(new ApiError(503, 'req-1'));

    renderScreen();

    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'east' } });
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Использовать демо-набор' })));

    await waitFor(() =>
      expect(screen.getByText(/Сервис временно недоступен, попробуйте ещё раз/)).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });
});
