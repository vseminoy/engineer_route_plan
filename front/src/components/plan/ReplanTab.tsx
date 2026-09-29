import { useState } from 'react';
import { useReplan } from '@/queries/useReplan';
import type { DonePlan, EngineerRoster, ReplanEvent, TicketSummary } from '@/types/domain';

type EventKind = 'new_urgent' | 'cancel' | 'unavailable';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  ticketById: Map<number, TicketSummary>;
  onReplanned: (newPlanId: number) => void;
}

function nowNaive(): Date {
  return new Date();
}

function toNaiveString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ReplanTab({ plan, roster, ticketById, onReplanned }: Props) {
  const [kind, setKind] = useState<EventKind>('new_urgent');
  const [address, setAddress] = useState('');
  const [cancelTicketId, setCancelTicketId] = useState<number | ''>('');
  const [unavailableEngineerId, setUnavailableEngineerId] = useState<number | ''>('');
  const replanMutation = useReplan(plan.planId);

  const assignedTickets = plan.engineers.flatMap((e) =>
    e.route.map((s) => ({ ticketId: s.ticketId, label: `${ticketById.get(s.ticketId)?.address ?? `№${s.ticketId}`} — ${e.name}` }))
  );

  function buildEvent(): ReplanEvent | null {
    const triggeredAt = nowNaive();
    if (kind === 'new_urgent') {
      if (!address.trim()) return null;
      const windowEnd = new Date(triggeredAt.getTime() + 100 * 60 * 1000); // BR-14: 100-minute SLA
      return {
        eventType: 'new_urgent_ticket',
        triggeredAt: toNaiveString(triggeredAt),
        ticket: {
          address: address.trim(),
          windowStart: toNaiveString(triggeredAt),
          windowEnd: toNaiveString(windowEnd),
          requiredSkill: 'emergency',
          durationMin: 80
        }
      };
    }
    if (kind === 'cancel') {
      if (cancelTicketId === '') return null;
      return { eventType: 'ticket_cancelled', triggeredAt: toNaiveString(triggeredAt), ticketId: cancelTicketId };
    }
    if (unavailableEngineerId === '') return null;
    return { eventType: 'engineer_unavailable', triggeredAt: toNaiveString(triggeredAt), engineerId: unavailableEngineerId };
  }

  function handleSubmit() {
    const event = buildEvent();
    if (!event) return;
    replanMutation.mutate(event, { onSuccess: (newPlan) => onReplanned(newPlan.planId) });
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label className="replan-radio">
          <input type="radio" checked={kind === 'new_urgent'} onChange={() => setKind('new_urgent')} />
          Новая срочная заявка
        </label>
        <label className="replan-radio">
          <input type="radio" checked={kind === 'cancel'} onChange={() => setKind('cancel')} />
          Отмена заявки
        </label>
        <label className="replan-radio">
          <input type="radio" checked={kind === 'unavailable'} onChange={() => setKind('unavailable')} />
          Недоступность бригады
        </label>
      </div>

      {kind === 'new_urgent' && (
        <div className="replan-fields">
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Адрес
            <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Например, ул. Наличная, 20" />
          </label>
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Навык: <strong style={{ color: 'var(--color-text-primary)' }}>Авария</strong> (фиксировано)
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Норматив на объекте: <strong style={{ color: 'var(--color-text-primary)' }}>80 мин</strong>
          </div>
        </div>
      )}

      {kind === 'cancel' && (
        <div className="replan-fields">
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Заявка для отмены
            <select value={cancelTicketId} onChange={(e) => setCancelTicketId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Выберите заявку…</option>
              {assignedTickets.map((t) => (
                <option key={t.ticketId} value={t.ticketId}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {kind === 'unavailable' && (
        <div className="replan-fields">
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Бригада недоступна
            <select value={unavailableEngineerId} onChange={(e) => setUnavailableEngineerId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Выберите бригаду…</option>
              {roster.map((r) => (
                <option key={r.engineerId} value={r.engineerId}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <button className="btn-primary" onClick={handleSubmit} disabled={replanMutation.isPending}>
        {replanMutation.isPending ? 'Перестраиваем…' : 'Перестроить план'}
      </button>
    </>
  );
}
