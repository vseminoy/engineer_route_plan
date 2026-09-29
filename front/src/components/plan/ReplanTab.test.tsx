import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReplanTab } from './ReplanTab';
import { ApiError } from '@/api/client';
import type { DonePlan, Plan, TicketSummary } from '@/types/domain';

const replanMock = vi.fn();
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>();
  return { ...actual, replan: (...args: unknown[]) => replanMock(...args) };
});

const emptyMetrics = {
  engineersUsed: 0,
  totalDistanceKm: 0,
  distanceByEngineer: {},
  assignedCount: 0,
  unassignedCount: 0,
  idleTimeByEngineerMin: {}
};

function donePlanResult(planId: number): Plan {
  return {
    planId,
    algorithm: 'or_tools',
    status: 'done',
    region: 'east',
    engineerSetId: 1,
    engineers: [],
    unassigned: [],
    metrics: emptyMetrics
  };
}

const plan: DonePlan = {
  planId: 42,
  algorithm: 'or_tools',
  engineerSetId: 1,
  engineers: [
    {
      engineerId: 3,
      name: 'Бригада Соколов',
      route: [
        {
          ticketId: 101,
          sequenceNo: 1,
          plannedArrival: '2026-08-17T10:05:00',
          travelTimeMin: 10,
          travelDistanceKm: 2,
          explanation: 'Назначена бригада «Соколов».'
        }
      ],
      totalDistanceKm: 2,
      totalTravelTimeMin: 10,
      idleTimeMin: 0
    }
  ],
  unassigned: [],
  metrics: { ...emptyMetrics, engineersUsed: 1, assignedCount: 1 }
};

const ticketById = new Map<number, TicketSummary>([
  [
    101,
    {
      ticketId: 101,
      requiredSkill: 'local_work',
      priority: 3,
      address: 'ул. Тест, 1',
      windowStartMin: 0,
      windowEndMin: 60,
      durationMin: 30,
      status: 'sent',
      lat: null,
      lon: null
    }
  ]
]);

function renderTab() {
  const onReplanned = vi.fn();
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <ReplanTab plan={plan} ticketById={ticketById} onReplanned={onReplanned} />
    </QueryClientProvider>
  );
  return { onReplanned };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('ReplanTab — new_urgent_ticket', () => {
  it('rejects an out-of-range latitude before it is sent, and does not call replan', async () => {
    renderTab();
    fireEvent.change(screen.getByLabelText('Адрес'), { target: { value: 'ул. Ленина, 1' } });
    fireEvent.change(screen.getByLabelText('Широта'), { target: { value: '999' } });
    fireEvent.change(screen.getByLabelText('Долгота'), { target: { value: '37.61' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(await screen.findByText('Too big: expected number to be <=90')).toBeInTheDocument();
    expect(replanMock).not.toHaveBeenCalled();
  });

  it('submits a valid event and hands the new plan id to onReplanned', async () => {
    replanMock.mockResolvedValue(donePlanResult(55));
    const { onReplanned } = renderTab();

    fireEvent.change(screen.getByLabelText('Адрес'), { target: { value: 'ул. Ленина, 1' } });
    fireEvent.change(screen.getByLabelText('Широта'), { target: { value: '55.75' } });
    fireEvent.change(screen.getByLabelText('Долгота'), { target: { value: '37.61' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    await waitFor(() => expect(onReplanned).toHaveBeenCalledWith(55));
    expect(replanMock).toHaveBeenCalledWith(
      42,
      expect.objectContaining({ eventType: 'new_urgent_ticket', address: 'ул. Ленина, 1', lat: 55.75, lon: 37.61 })
    );
  });

  it('shows a full-screen retry notice on a 503, and retries the same event on demand', async () => {
    replanMock.mockRejectedValueOnce(new ApiError(503, 'req-2'));
    renderTab();

    fireEvent.change(screen.getByLabelText('Адрес'), { target: { value: 'ул. Ленина, 1' } });
    fireEvent.change(screen.getByLabelText('Широта'), { target: { value: '55.75' } });
    fireEvent.change(screen.getByLabelText('Долгота'), { target: { value: '37.61' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(await screen.findByText(/Сервис временно недоступен, попробуйте ещё раз/)).toBeInTheDocument();

    replanMock.mockResolvedValueOnce(donePlanResult(57));
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));

    await waitFor(() => expect(replanMock).toHaveBeenCalledTimes(2));
  });
});

describe('ReplanTab — ticket_cancelled', () => {
  it('rejects submitting with no ticket selected, and does not call replan', () => {
    renderTab();
    fireEvent.click(screen.getByRole('radio', { name: 'Отмена заявки' }));
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(screen.getByText('Invalid input: expected number, received NaN')).toBeInTheDocument();
    expect(replanMock).not.toHaveBeenCalled();
  });

  it('submits a valid cancel event for the selected ticket', async () => {
    replanMock.mockResolvedValue(donePlanResult(56));
    const { onReplanned } = renderTab();

    fireEvent.click(screen.getByRole('radio', { name: 'Отмена заявки' }));
    fireEvent.change(screen.getByLabelText('Заявка для отмены'), { target: { value: '101' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    await waitFor(() => expect(onReplanned).toHaveBeenCalledWith(56));
    expect(replanMock).toHaveBeenCalledWith(42, expect.objectContaining({ eventType: 'ticket_cancelled', ticketId: 101 }));
  });

  it('shows the conflict message when the ticket is not yet marked cancelled', async () => {
    replanMock.mockRejectedValue(new ApiError(409, 'req-1'));
    renderTab();

    fireEvent.click(screen.getByRole('radio', { name: 'Отмена заявки' }));
    fireEvent.change(screen.getByLabelText('Заявка для отмены'), { target: { value: '101' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(await screen.findByText('Заявка ещё не отмечена отменённой — сначала измените её статус')).toBeInTheDocument();
  });
});

describe('ReplanTab — engineer_unavailable', () => {
  it('rejects submitting with no engineer selected, and does not call replan', () => {
    renderTab();
    fireEvent.click(screen.getByRole('radio', { name: 'Недоступность бригады' }));
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(screen.getByText('Invalid input: expected number, received NaN')).toBeInTheDocument();
    expect(replanMock).not.toHaveBeenCalled();
  });

  it('submits a valid engineer_unavailable event for the selected engineer', async () => {
    replanMock.mockResolvedValue(donePlanResult(58));
    const { onReplanned } = renderTab();

    fireEvent.click(screen.getByRole('radio', { name: 'Недоступность бригады' }));
    fireEvent.change(screen.getByLabelText('Бригада недоступна'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    await waitFor(() => expect(onReplanned).toHaveBeenCalledWith(58));
    expect(replanMock).toHaveBeenCalledWith(
      42,
      expect.objectContaining({ eventType: 'engineer_unavailable', engineerId: 3 })
    );
  });

  it('shows a 404 as "not found" when the engineer does not exist', async () => {
    replanMock.mockRejectedValue(new ApiError(404, 'req-3'));
    renderTab();

    fireEvent.click(screen.getByRole('radio', { name: 'Недоступность бригады' }));
    fireEvent.change(screen.getByLabelText('Бригада недоступна'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Перестроить план' }));

    expect(await screen.findByText('Не найдено')).toBeInTheDocument();
  });
});
