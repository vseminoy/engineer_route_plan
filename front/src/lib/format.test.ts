import { describe, expect, it } from 'vitest';
import { minutesSinceMidnight, timeOnly } from './format';

describe('timeOnly', () => {
  it('extracts hours:minutes from a full naive datetime with seconds', () => {
    expect(timeOnly('2026-08-17T10:05:00')).toBe('10:05');
  });

  it('leaves a bare HH:MM unchanged', () => {
    expect(timeOnly('10:05')).toBe('10:05');
  });

  it('returns the input as-is when no time is found', () => {
    expect(timeOnly('n/a')).toBe('n/a');
  });
});

describe('minutesSinceMidnight', () => {
  it('reads hours:minutes from a full naive datetime with seconds', () => {
    expect(minutesSinceMidnight('2026-08-17T10:05:00')).toBe(605);
  });
});
