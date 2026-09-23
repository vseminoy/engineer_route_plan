import { skillLabel, unassignedReasonHeading } from '@/lib/labels';
import { minutesToTimeLabel } from '@/lib/format';
import type { TicketSummary, UnassignedTicket } from '@/types/domain';

interface Props {
  ticket: UnassignedTicket;
  summary: TicketSummary | undefined;
  onClick: () => void;
}

export function UnassignedTicketCard({ ticket, summary, onClick }: Props) {
  return (
    <div className="unassigned-card" onClick={onClick}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>{summary?.address ?? `Заявка №${ticket.ticketId}`}</span>
        {summary?.priority === 'urgent' && <span className="urgent-badge">Срочно</span>}
      </div>
      {summary && (
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          Навык: {skillLabel(summary.requiredSkill)} · окно {minutesToTimeLabel(summary.windowStartMin)}–
          {minutesToTimeLabel(summary.windowEndMin)}
        </div>
      )}
      <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.4 }}>
        {unassignedReasonHeading[ticket.reasonCode]}
      </div>
    </div>
  );
}
