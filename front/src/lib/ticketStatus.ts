import type { TicketStatus } from '@/types/domain';

// PATCH /tickets/{id}/status's own transition rules, mirrored here so the UI
// only offers a status a dispatcher could actually pick — the backend is the
// real gate and re-validates independently. Forward moves may skip steps
// (sent -> completed); cancelled is reachable from anywhere open; overdue only
// from not_sent/sent/en_route; completed and cancelled are closed (no move out).
const FORWARD_CHAIN: TicketStatus[] = ['not_sent', 'sent', 'en_route', 'in_progress', 'completed'];
const OVERDUE_SOURCES: TicketStatus[] = ['not_sent', 'sent', 'en_route'];

export function isClosedStatus(status: TicketStatus): boolean {
  return status === 'completed' || status === 'cancelled';
}

export function allowedNextStatuses(status: TicketStatus): TicketStatus[] {
  if (status === 'overdue') return ['en_route', 'in_progress', 'completed', 'cancelled'];
  if (isClosedStatus(status)) return [];

  const next = [...FORWARD_CHAIN.slice(FORWARD_CHAIN.indexOf(status) + 1), 'cancelled' as TicketStatus];
  if (OVERDUE_SOURCES.includes(status)) next.push('overdue');
  return next;
}
