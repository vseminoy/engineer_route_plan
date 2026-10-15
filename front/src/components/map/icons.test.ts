import { describe, expect, it } from 'vitest';
import { buildTicketIcon } from './icons';

const base = {
  color: '#2a78d6',
  urgent: false,
  emergency: false,
  unassigned: false,
  status: 'sent' as const
};

describe('buildTicketIcon', () => {
  it('writes the stop\'s sequence number inside the body circle when given one', () => {
    const icon = buildTicketIcon({ ...base, sequenceNo: 3 });
    const html = (icon.options as { html: string }).html;

    expect(html).toContain('>3<');
  });

  it('renders no number for a stop with no sequenceNo (unassigned tickets)', () => {
    const icon = buildTicketIcon({ ...base, unassigned: true });
    const html = (icon.options as { html: string }).html;

    expect(html).not.toContain('<text');
  });

  it('moves the emergency glyph to a corner badge so it never overlaps the sequence number', () => {
    const icon = buildTicketIcon({ ...base, emergency: true, sequenceNo: 7 });
    const html = (icon.options as { html: string }).html;

    expect(html).toContain('>7<');
    expect(html).toContain('Экстренная');
    // The number sits at the body circle's center (16,16); the emergency badge must not.
    expect(html).toContain('cx="8" cy="8"');
  });
});
