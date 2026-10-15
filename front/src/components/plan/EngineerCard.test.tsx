import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EngineerCard } from './EngineerCard';
import type { EngineerRoute, TicketSummary } from '@/types/domain';

const engineer: EngineerRoute = {
  engineerId: 2,
  name: 'Бригада 2',
  route: [
    {
      ticketId: 100,
      sequenceNo: 1,
      plannedArrival: '2026-09-01T13:10:00', // arrives before the 14:00 window opens
      travelTimeMin: 20,
      travelDistanceKm: 5,
      explanation: 'назначено'
    }
  ],
  totalDistanceKm: 5,
  totalTravelTimeMin: 20,
  idleTimeMin: 0
};

const twoStopEngineer: EngineerRoute = {
  ...engineer,
  route: [
    { ...engineer.route[0], ticketId: 100, sequenceNo: 1 },
    { ...engineer.route[0], ticketId: 101, sequenceNo: 2 }
  ]
};

const ticket: TicketSummary = {
  ticketId: 100,
  requiredSkill: 'local_work',
  priority: 1,
  address: 'Кашира, ул. Победы, д. 9',
  windowStartMin: 14 * 60,
  windowEndMin: 16 * 60,
  durationMin: 30,
  status: 'sent',
  lat: 55.0,
  lon: 38.2
};

describe('EngineerCard', () => {
  it('shows the stop as starting at the window open, not at the raw (earlier) arrival', () => {
    render(
      <EngineerCard
        engineer={engineer}
        roster={undefined}
        color="#000"
        ticketById={new Map([[100, ticket]])}
        diffTags={new Map()}
        selected={false}
        onSelect={vi.fn()}
        onStopClick={vi.fn()}
      />
    );

    // The brigade physically arrives at 13:10 and waits for the 14:00 window — the
    // displayed service interval must not precede the window line shown right below it.
    expect(screen.getByText('14:00–14:30')).toBeInTheDocument();
    expect(screen.queryByText('13:10–13:40')).not.toBeInTheDocument();
    expect(screen.getByText(/окно 14:00–16:00/)).toBeInTheDocument();
  });

  it('numbers each stop with its position in the route, same ordinal as its marker on the map', () => {
    render(
      <EngineerCard
        engineer={twoStopEngineer}
        roster={undefined}
        color="#000"
        ticketById={new Map([[100, ticket], [101, { ...ticket, ticketId: 101 }]])}
        diffTags={new Map()}
        selected={false}
        onSelect={vi.fn()}
        onStopClick={vi.fn()}
      />
    );

    const numbers = screen.getAllByText(/^[12]$/).map((el) => el.textContent);
    expect(numbers).toEqual(['1', '2']);
  });
});
