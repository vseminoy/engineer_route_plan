import L from 'leaflet';

// Marker shape encodes priority/status alongside color, never color alone:
// urgent gets a ring and emergency gets a bolt glyph on top of the identity
// color, not just a hue change.
interface TicketIconOptions {
  color: string;
  urgent: boolean;
  emergency: boolean;
  unassigned: boolean;
  diffHighlight?: boolean;
}

export function buildTicketIcon({ color, urgent, emergency, unassigned, diffHighlight }: TicketIconOptions) {
  const size = 32;
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

  return L.divIcon({
    className: 'ticket-marker',
    html: `<svg width="${size}" height="${size}" viewBox="0 0 32 32">${diffRing}${urgentRing}${body}${bolt}</svg>`,
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
