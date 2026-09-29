import { describe, expect, it } from 'vitest';
import { RUNNING_POLL_INTERVAL_MS, planRefetchInterval } from './usePlan';

describe('planRefetchInterval', () => {
  it('keeps polling every 2s while the build is running', () => {
    expect(planRefetchInterval('running')).toBe(RUNNING_POLL_INTERVAL_MS);
  });

  it('stops polling once the status is done', () => {
    expect(planRefetchInterval('done')).toBe(false);
  });

  it('stops polling once the status is failed', () => {
    expect(planRefetchInterval('failed')).toBe(false);
  });

  it('stops polling before the first response arrives (no data yet)', () => {
    expect(planRefetchInterval(undefined)).toBe(false);
  });
});
