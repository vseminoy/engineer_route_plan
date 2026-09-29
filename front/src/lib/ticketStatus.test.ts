import { describe, expect, it } from 'vitest';
import { allowedNextStatuses, isClosedStatus } from './ticketStatus';

describe('allowedNextStatuses', () => {
  it('allows forward moves (including skipping a step), cancel, and overdue from not_sent', () => {
    expect(allowedNextStatuses('not_sent')).toEqual(['sent', 'en_route', 'in_progress', 'completed', 'cancelled', 'overdue']);
  });

  it('allows forward moves, cancel, and overdue from en_route', () => {
    expect(allowedNextStatuses('en_route')).toEqual(['in_progress', 'completed', 'cancelled', 'overdue']);
  });

  it('does not offer overdue once work has started (in_progress)', () => {
    expect(allowedNextStatuses('in_progress')).toEqual(['completed', 'cancelled']);
  });

  it('lets overdue return to en_route/in_progress/completed or cancel', () => {
    expect(allowedNextStatuses('overdue')).toEqual(['en_route', 'in_progress', 'completed', 'cancelled']);
  });

  it('offers nothing once closed (completed, cancelled)', () => {
    expect(allowedNextStatuses('completed')).toEqual([]);
    expect(allowedNextStatuses('cancelled')).toEqual([]);
  });
});

describe('isClosedStatus', () => {
  it('is true only for completed and cancelled', () => {
    expect(isClosedStatus('completed')).toBe(true);
    expect(isClosedStatus('cancelled')).toBe(true);
    expect(isClosedStatus('overdue')).toBe(false);
    expect(isClosedStatus('not_sent')).toBe(false);
  });
});
