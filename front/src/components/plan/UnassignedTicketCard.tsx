import { SkillIcons } from './SkillIcons';
import { unassignedReasonHeading } from '@/lib/labels';
import { minutesToTimeLabel } from '@/lib/format';
import { URGENT_PRIORITY, type TicketSummary, type UnassignedTicket } from '@/types/domain';

interface Props {
  ticket: UnassignedTicket;
  summary: TicketSummary | undefined;
  onClick: () => void;
}

export function UnassignedTicketCard({ ticket, summary, onClick }: Props) {
  return (
    <div className="unassigned-card" onClick={onClick}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, minWidth: 0 }}>
          {summary && <SkillIcons skills={[summary.requiredSkill]} />}
          <span style={{ fontSize: 14, fontWeight: 600, minWidth: 0, overflowWrap: 'break-word' }}>
            {summary?.address ?? `Заявка №${ticket.ticketId}`}
          </span>
        </div>
        {summary?.priority === URGENT_PRIORITY && (
          <span className="urgent-badge" style={{ flexShrink: 0 }}>
            Срочно
          </span>
        )}
      </div>
      {summary && (
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          Окно {minutesToTimeLabel(summary.windowStartMin)}–{minutesToTimeLabel(summary.windowEndMin)}
        </div>
      )}
      <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.4 }}>
        {unassignedReasonHeading[ticket.reasonCode]}
      </div>
    </div>
  );
}
