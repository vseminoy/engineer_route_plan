import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IdleTimeBlock } from './IdleTimeBlock';
import type { EngineerRoute } from '@/types/domain';

const used: EngineerRoute = {
  engineerId: 1,
  name: 'Бригада 1',
  route: [
    { ticketId: 1, sequenceNo: 1, plannedArrival: '2026-08-17T10:00:00', travelTimeMin: 10, travelDistanceKm: 3, explanation: '' },
    { ticketId: 2, sequenceNo: 2, plannedArrival: '2026-08-17T11:00:00', travelTimeMin: 10, travelDistanceKm: 4, explanation: '' }
  ],
  totalDistanceKm: 12.5,
  totalTravelTimeMin: 20,
  idleTimeMin: 35
};

const unused: EngineerRoute = {
  engineerId: 2,
  name: 'Бригада 2',
  route: [],
  totalDistanceKm: 0,
  totalTravelTimeMin: 0,
  idleTimeMin: 480
};

describe('IdleTimeBlock', () => {
  it('renders a borderless table with one row per brigade, used and unused alike, with no label for the name/vehicle/skills columns', () => {
    render(<IdleTimeBlock engineers={[used, unused]} roster={[]} />);

    expect(screen.queryByText('Бригада')).not.toBeInTheDocument();
    expect(screen.queryByText('Транспорт')).not.toBeInTheDocument();
    expect(screen.queryByText('Навыки')).not.toBeInTheDocument();
    expect(screen.getByText('Смена')).toBeInTheDocument();
    expect(screen.getByText('Заявки')).toBeInTheDocument();
    expect(screen.getByText('Пробег')).toBeInTheDocument();
    expect(screen.getByText('Простой')).toBeInTheDocument();

    const usedRow = screen.getByText('Бригада 1').closest('tr');
    expect(usedRow?.textContent).toContain('2');
    expect(usedRow?.textContent).toContain('12,5 км');
    expect(usedRow?.textContent).toContain('35 мин');

    const unusedRow = screen.getByText('Бригада 2').closest('tr');
    expect(unusedRow?.textContent).toContain('0,0 км');
    expect(unusedRow?.textContent).toContain('480 мин');
  });

  it('sinks unused brigades to the bottom of the list and greys them out, regardless of input order', () => {
    render(<IdleTimeBlock engineers={[unused, used]} roster={[]} />);

    const rows = screen.getAllByRole('row').slice(1); // drop the header row
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Бригада 1'),
      expect.stringContaining('Бригада 2')
    ]);
    expect(rows[1]).toHaveClass('brigade-table__row--idle');
    expect(rows[0]).not.toHaveClass('brigade-table__row--idle');
  });
});
