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
    assignedCount: 43,
    unassignedCount: 2,
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

    const { container } = render(<MetricsTab plan={plan} roster={[]} engineerSetName="13 бригад" />);

    expect(screen.getByText('Сравнение в пределах набора «13 бригад»')).toBeInTheDocument();
    expect(screen.getByText('Заявок в плане: 45')).toBeInTheDocument();
    expect(screen.getByText('Неназначено заявок')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('baseline: 6')).toBeInTheDocument();

    // "Заявок в плане" belongs under the engineer-set line, not inside the unassigned-count row.
    const rows = container.querySelectorAll('.metric-row');
    const unassignedRow = Array.from(rows).find((r) => r.textContent?.includes('Неназначено заявок'));
    expect(unassignedRow?.textContent).not.toContain('Заявок в плане');
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

    const rows = container.querySelectorAll('.metric-row');
    const unassignedRow = Array.from(rows).find((r) => r.textContent?.includes('Неназначено заявок'));
    expect(unassignedRow?.querySelector('.metric-delta--bad')).not.toBeNull();
    expect(unassignedRow?.querySelector('.metric-delta--good')).toBeNull();
  });
});
