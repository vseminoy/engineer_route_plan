import L from 'leaflet';
import { ticketStatusLabel } from '@/lib/labels';
import type { TicketStatus } from '@/types/domain';

// Marker shape encodes priority/status alongside color, never color alone:
// urgent gets a ring and emergency gets a bolt glyph on top of the identity
// color, not just a hue change.
interface TicketIconOptions {
  color: string;
  urgent: boolean;
  emergency: boolean;
  unassigned: boolean;
  status: TicketStatus;
  diffHighlight?: boolean;
  selected?: boolean;
}

// Small badge at the marker's bottom-right corner, on top of the body circle,
// so ticket status stays legible alongside priority (ring) and identity
// (fill color) instead of competing with them for the same shape.
const STATUS_BADGE_COLOR: Record<TicketStatus, string> = {
  not_sent: '#8A8F98',
  sent: '#2A78D6',
  en_route: '#2A78D6',
  in_progress: '#8A5A00',
  completed: '#006300',
  cancelled: '#9AA0AA',
  overdue: '#D03B3B'
};

const STATUS_BADGE_GLYPH: Record<TicketStatus, string> = {
  not_sent: '<circle r="2" fill="none" stroke-width="1.3"/>',
  sent: '<path d="M-2.4,-2 L2.6,0 L-2.4,2 L-1.2,0 Z" stroke="none"/>',
  en_route:
    '<path d="M-2,-2.2 L1.6,0 L-2,2.2" fill="none" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
  in_progress: '<path d="M0,-3 A3,3 0 0 1 0,3 Z" stroke="none"/>',
  completed:
    '<path d="M-2.4,0.2 L-0.6,2 L2.4,-2.2" fill="none" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  cancelled: '<path d="M-2,-2 L2,2 M-2,2 L2,-2" stroke-width="1.4" stroke-linecap="round"/>',
  overdue:
    '<line x1="0" y1="-2.6" x2="0" y2="0.6" stroke-width="1.5" stroke-linecap="round"/><circle cx="0" cy="2.4" r="0.9" stroke="none"/>'
};

function buildStatusBadge(status: TicketStatus): string {
  const color = STATUS_BADGE_COLOR[status];
  const glyph = STATUS_BADGE_GLYPH[status];
  return (
    '<circle cx="24" cy="24" r="6.5" fill="#FFFFFF" stroke="' +
    color +
    '" stroke-width="1.5"/>' +
    '<g transform="translate(24,24)" stroke="' +
    color +
    '" fill="' +
    color +
    '"><title>' +
    ticketStatusLabel[status] +
    '</title>' +
    glyph +
    '</g>'
  );
}

export function buildTicketIcon({ color, urgent, emergency, unassigned, status, diffHighlight, selected }: TicketIconOptions) {
  // Selection scales the whole marker up (viewBox stays 32x32, the pixel
  // size grows) rather than adding another same-radius ring, so it never
  // collides with the diff/urgent rings and reads as "this one" at a glance.
  const size = selected ? 44 : 32;
  const pulse = selected
    ? '<circle class="ticket-marker__pulse" cx="16" cy="16" r="13" fill="none" stroke="#12151A" stroke-width="2"/>'
    : '';
  const diffRing = diffHighlight
    ? '<circle cx="16" cy="16" r="15" fill="none" stroke="#2A78D6" stroke-width="2" stroke-dasharray="4,3"/>'
    : '';
  const urgentRing = urgent
    ? '<circle cx="16" cy="16" r="12" fill="none" stroke="#D03B3B" stroke-width="3"/>'
    : '';
  const body = unassigned
    ? '<circle cx="16" cy="16" r="9" fill="#EEF1F5" stroke="#9AA0AA" stroke-width="2" stroke-dasharray="3,3"/><line x1="12" y1="16" x2="20" y2="16" stroke="#9AA0AA" stroke-width="2"/>'
    : `<circle cx="16" cy="16" r="9" fill="${color}" stroke="#FFFFFF" stroke-width="2"/>`;
  const bolt =
    emergency && !unassigned
      ? '<path d="M15,9 L11,17 L15,17 L14,23 L21,15 L17,15 L18,9 Z" fill="#FFFFFF" transform="translate(-2,-1) scale(0.6)"/>'
      : '';
  const statusBadge = buildStatusBadge(status);

  return L.divIcon({
    className: `ticket-marker${selected ? ' ticket-marker--selected' : ''}`,
    html: `<svg width="${size}" height="${size}" viewBox="0 0 32 32">${pulse}${diffRing}${urgentRing}${body}${bolt}${statusBadge}</svg>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2]
  });
}

export function buildOfficeIcon() {
  return L.divIcon({
    className: 'office-marker',
    html:
      '<svg width="30" height="30" viewBox="0 0 30 30">' +
      '<circle cx="15" cy="15" r="14" fill="#12151A"/>' +
      '<path d="M9,17 L15,11 L21,17 L21,21 L17,21 L17,16 L13,16 L13,21 L9,21 Z" fill="#FFFFFF"/>' +
      '</svg>',
    iconSize: [30, 30],
    iconAnchor: [15, 15]
  });
}
