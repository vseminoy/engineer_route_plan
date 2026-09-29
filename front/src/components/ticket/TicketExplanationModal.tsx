import { useState } from 'react';
import { getEngineerColor } from '@/lib/colors';
import { describeError, skillLabel, unassignedReasonHeading } from '@/lib/labels';
import { minutesToTimeLabel, timeOnly } from '@/lib/format';
import { useSetTicketStatus } from '@/queries/useSetTicketStatus';
import { TicketStatusControl } from './TicketStatusControl';
import { URGENT_PRIORITY, type Plan, type RegionCode, type TicketStatus, type TicketSummary } from '@/types/domain';

interface Props {
  plan: Plan;
  ticketById: Map<number, TicketSummary>;
  ticketId: number;
  region: RegionCode | null;
  onClose: () => void;
}

// 06_spec_frontend.md §3.5 — assigned block (engineer, arrival, full
// explanation) or unassigned block (reason heading + full explanation),
// never truncated (NFR-01/NFR-07). Full-screen on mobile via CSS (≤767px).
export function TicketExplanationModal({ plan, ticketById, ticketId, region, onClose }: Props) {
  const summary = ticketById.get(ticketId);
  const setStatus = useSetTicketStatus(plan.planId, region);
  const [statusError, setStatusError] = useState<string | null>(null);

  function handleStatusChange(next: TicketStatus) {
    setStatusError(null);
    setStatus.mutate(
      { ticketId, status: next },
      { onError: (err) => setStatusError(describeError(err, 'PATCH /tickets/{id}/status')) }
    );
  }

  let assignment: { engineerId: number; engineerName: string; eta: string; explanation: string } | null = null;
  for (const engineer of plan.engineers) {
    const stop = engineer.route.find((s) => s.ticketId === ticketId);
    if (stop) {
      assignment = { engineerId: engineer.engineerId, engineerName: engineer.name, eta: timeOnly(stop.plannedArrival), explanation: stop.explanation };
      break;
    }
  }
  const unassigned = plan.unassigned.find((u) => u.ticketId === ticketId);

  const urgent = summary?.priority === URGENT_PRIORITY;
  const windowText = summary ? `${minutesToTimeLabel(summary.windowStartMin)}–${minutesToTimeLabel(summary.windowEndMin)}` : '—';
  const skill = summary ? skillLabel(summary.requiredSkill) : '—';

  return (
    <div className="ticket-modal__overlay" role="dialog" aria-modal="true">
      <div className="ticket-modal__card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Заявка</div>
            <h2 style={{ margin: '4px 0 0', fontSize: 20, fontWeight: 600 }}>{summary?.address ?? `Заявка №${ticketId}`}</h2>
          </div>
          <button
            aria-label="Закрыть"
            onClick={onClose}
            style={{ width: 32, height: 32, borderRadius: 8, border: '1px solid rgba(18,21,26,0.12)', background: '#fff', cursor: 'pointer' }}
          >
            <svg width={14} height={14} viewBox="0 0 14 14">
              <path d="M1,1 L13,13 M13,1 L1,13" stroke="#5B6270" strokeWidth={1.6} strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {urgent && (
          <div className="urgent-badge">
            <svg width={12} height={12} viewBox="0 0 12 12">
              <path d="M6,1 L11,10 L1,10 Z" fill="none" stroke="#B23A2B" strokeWidth={1.3} strokeLinejoin="round" />
              <line x1={6} y1={4.5} x2={6} y2={7} stroke="#B23A2B" strokeWidth={1.3} />
              <circle cx={6} cy={8.4} r={0.6} fill="#B23A2B" />
            </svg>
            Срочная заявка
          </div>
        )}

        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 14, color: 'var(--color-text-secondary)' }}>
          <span>Окно: {windowText}</span>
          <span>Навык: {skill}</span>
        </div>

        {summary && (
          <TicketStatusControl
            status={summary.status}
            pending={setStatus.isPending}
            error={statusError}
            onChange={handleStatusChange}
          />
        )}

        {assignment && (
          <>
            <div style={{ background: '#f4f6f8', borderRadius: 12, padding: 16, display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: getEngineerColor(assignment.engineerId), flexShrink: 0 }} />
              <strong>{assignment.engineerName}</strong>
              <span style={{ color: 'var(--color-text-secondary)' }}>· прибытие {assignment.eta}</span>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 6 }}>Почему эта бригада</div>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5 }}>{assignment.explanation}</p>
            </div>
          </>
        )}

        {unassigned && (
          <div style={{ background: 'var(--color-danger-bg)', border: '1px solid #F3D3CC', borderRadius: 12, padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-danger-text)' }}>{unassignedReasonHeading[unassigned.reasonCode]}</div>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>{unassigned.explanation}</p>
          </div>
        )}
      </div>
    </div>
  );
}
