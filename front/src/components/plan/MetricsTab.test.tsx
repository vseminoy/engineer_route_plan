import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MetricsTab } from './MetricsTab';
import type { DonePlan } from '@/types/domain';

const usePlanCompareMock = vi.fn();
vi.mock('@/queries/usePlanCompare', () => ({
  usePlanCompare: (...args: unknown[]) => usePlanCompareMock(...args)
}));

const plan: DonePlan = {
  planId: 42,
  algorithm: 'or_tools',
  engineerSetId: 1,
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
};

describe('MetricsTab', () => {
  it('renders a third card for unassignedCount, alongside the two mandatory metrics', () => {
    usePlanCompareMock.mockReturnValue({
      data: {
        engineersUsed: { main: 9, baseline: 13, delta: -4 },
        totalDistanceKm: { main: 187.3, baseline: 244.9, delta: -57.6 },
        unassignedCount: { main: 2, baseline: 6, delta: -4 }
      },
      isError: false,
      baselineUnavailable: false
    });

    render(<MetricsTab plan={plan} roster={[]} />);

    expect(screen.getByText('Неназначено заявок')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('baseline: 6')).toBeInTheDocument();
  });

  it('marks a higher unassigned count than the baseline as a regression, not an improvement', () => {
    usePlanCompareMock.mockReturnValue({
      data: {
        engineersUsed: { main: 9, baseline: 13, delta: -4 },
        totalDistanceKm: { main: 187.3, baseline: 244.9, delta: -57.6 },
        unassignedCount: { main: 6, baseline: 2, delta: 4 }
      },
      isError: false,
      baselineUnavailable: false
    });

    const { container } = render(<MetricsTab plan={plan} roster={[]} />);

    const cards = container.querySelectorAll('.metric-card');
    const unassignedCard = Array.from(cards).find((c) => c.textContent?.includes('Неназначено заявок'));
    expect(unassignedCard?.querySelector('.metric-delta--bad')).not.toBeNull();
    expect(unassignedCard?.querySelector('.metric-delta--good')).toBeNull();
  });
});
