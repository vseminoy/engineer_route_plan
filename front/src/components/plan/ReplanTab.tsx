import { useState } from 'react';
import { useReplan } from '@/queries/useReplan';
import { replanEventToRequest } from '@/api/endpoints';
import { ReplanPlanBody } from '@/api/generated/zod/engineerRoutePlanAPI';
import { ApiError } from '@/api/client';
import { describeError } from '@/lib/labels';
import { fieldErrorsFromApi, fieldErrorsFromZod, isFieldErrors, type FieldErrorMap } from '@/lib/fieldErrors';
import { ErrorToast } from '@/components/common/ErrorToast';
import { FullScreenErrorNotice } from '@/components/common/FullScreenErrorNotice';
import type { DonePlan, ReplanEvent, TicketSummary } from '@/types/domain';

type EventKind = ReplanEvent['eventType'];

interface Props {
  plan: DonePlan;
  ticketById: Map<number, TicketSummary>;
  onReplanned: (newPlanId: number) => void;
}

const ENDPOINT = 'POST /plan/{id}/replan';

// The three schema members this form raises — the contract's oneOf order is
// [new_urgent_ticket, new_ticket, ticket_cancelled, engineer_unavailable];
// new_ticket has no form.
const NEW_URGENT_TICKET_SCHEMA = ReplanPlanBody.options[0];
const TICKET_CANCELLED_SCHEMA = ReplanPlanBody.options[2];
const ENGINEER_UNAVAILABLE_SCHEMA = ReplanPlanBody.options[3];

function nowNaive(): Date {
  return new Date();
}

function toLocalDateTimeString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function ReplanTab({ plan, ticketById, onReplanned }: Props) {
  const [kind, setKind] = useState<EventKind>('new_urgent_ticket');
  const [address, setAddress] = useState('');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [reactionMin, setReactionMin] = useState('');
  const [cancelTicketId, setCancelTicketId] = useState<number | ''>('');
  const [unavailableEngineerId, setUnavailableEngineerId] = useState<number | ''>('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrorMap>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const replanMutation = useReplan(plan.planId);

  const assignedTickets = plan.engineers.flatMap((e) =>
    e.route.map((s) => ({ ticketId: s.ticketId, label: `${ticketById.get(s.ticketId)?.address ?? `№${s.ticketId}`} — ${e.name}` }))
  );

  // plan.engineers already lists every engineer of the region (even ones with
  // an empty route), so it doubles as the roster for this picker.
  const engineerOptions = plan.engineers.map((e) => ({ engineerId: e.engineerId, name: e.name }));

  function selectKind(next: EventKind) {
    setKind(next);
    setFieldErrors({});
    setFormError(null);
  }

  function buildEvent(): ReplanEvent {
    const triggeredAt = toLocalDateTimeString(nowNaive());
    if (kind === 'new_urgent_ticket') {
      const reaction = reactionMin.trim() === '' ? undefined : Number(reactionMin);
      return {
        eventType: 'new_urgent_ticket',
        triggeredAt,
        address: address.trim(),
        lat: lat.trim() === '' ? NaN : Number(lat),
        lon: lon.trim() === '' ? NaN : Number(lon),
        ...(reaction !== undefined ? { reactionMin: reaction } : {})
      };
    }
    if (kind === 'ticket_cancelled') {
      return { eventType: 'ticket_cancelled', triggeredAt, ticketId: cancelTicketId === '' ? NaN : cancelTicketId };
    }
    return {
      eventType: 'engineer_unavailable',
      triggeredAt,
      engineerId: unavailableEngineerId === '' ? NaN : unavailableEngineerId
    };
  }

  function handleReplanError(err: unknown) {
    if (err instanceof ApiError && err.status === 400 && err.body) {
      const body = err.body;
      if (isFieldErrors(body)) {
        setFieldErrors((prev) => ({ ...prev, ...fieldErrorsFromApi(body) }));
      } else {
        setFormError(body.message);
      }
      return;
    }
    if (err instanceof ApiError && err.status === 503) {
      setServiceError(describeError(err, ENDPOINT));
      return;
    }
    setFormError(describeError(err, ENDPOINT));
  }

  function submitEvent(event: ReplanEvent) {
    replanMutation.mutate(event, {
      onSuccess: (newPlan) => onReplanned(newPlan.planId),
      onError: handleReplanError
    });
  }

  function handleSubmit() {
    setFormError(null);
    const event = buildEvent();
    const request = replanEventToRequest(event);
    const schema =
      event.eventType === 'new_urgent_ticket'
        ? NEW_URGENT_TICKET_SCHEMA
        : event.eventType === 'ticket_cancelled'
          ? TICKET_CANCELLED_SCHEMA
          : ENGINEER_UNAVAILABLE_SCHEMA;
    const parsed = schema.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setFieldErrors({});
    submitEvent(event);
  }

  function retry() {
    if (!replanMutation.variables) return;
    setServiceError(null);
    submitEvent(replanMutation.variables);
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label className="replan-radio">
          <input type="radio" checked={kind === 'new_urgent_ticket'} onChange={() => selectKind('new_urgent_ticket')} />
          Новая срочная заявка
        </label>
        <label className="replan-radio">
          <input type="radio" checked={kind === 'ticket_cancelled'} onChange={() => selectKind('ticket_cancelled')} />
          Отмена заявки
        </label>
        <label className="replan-radio">
          <input
            type="radio"
            checked={kind === 'engineer_unavailable'}
            onChange={() => selectKind('engineer_unavailable')}
          />
          Недоступность бригады
        </label>
      </div>

      {kind === 'new_urgent_ticket' && (
        <div className="replan-fields">
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Адрес
            <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Например, ул. Наличная, 20" />
          </label>
          {fieldErrors['ticket.address'] && (
            <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{fieldErrors['ticket.address']}</span>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)', flex: 1 }}>
              Широта
              <input type="number" step="any" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="55.75" />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)', flex: 1 }}>
              Долгота
              <input type="number" step="any" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="37.61" />
            </label>
          </div>
          {(fieldErrors['ticket.location.lat'] || fieldErrors['ticket.location.lon']) && (
            <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>
              {fieldErrors['ticket.location.lat'] ?? fieldErrors['ticket.location.lon']}
            </span>
          )}

          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Время реакции, мин (необязательно, 60–120, по умолчанию 120)
            <input type="number" min={60} max={120} value={reactionMin} onChange={(e) => setReactionMin(e.target.value)} placeholder="120" />
          </label>
          {fieldErrors.reaction_min && (
            <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{fieldErrors.reaction_min}</span>
          )}

          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Навык: <strong style={{ color: 'var(--color-text-primary)' }}>Авария</strong> (фиксировано)
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Норматив на объекте: <strong style={{ color: 'var(--color-text-primary)' }}>80 мин</strong> (считает сервер)
          </div>
        </div>
      )}

      {kind === 'ticket_cancelled' && (
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
          {fieldErrors.ticket_id && (
            <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{fieldErrors.ticket_id}</span>
          )}
        </div>
      )}

      {kind === 'engineer_unavailable' && (
        <div className="replan-fields">
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Бригада недоступна
            <select
              value={unavailableEngineerId}
              onChange={(e) => setUnavailableEngineerId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Выберите бригаду…</option>
              {engineerOptions.map((e) => (
                <option key={e.engineerId} value={e.engineerId}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          {fieldErrors.engineer_id && (
            <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{fieldErrors.engineer_id}</span>
          )}
        </div>
      )}

      <button className="btn-primary" onClick={handleSubmit} disabled={replanMutation.isPending}>
        {replanMutation.isPending ? 'Перестраиваем…' : 'Перестроить план'}
      </button>

      {formError && <ErrorToast message={formError} onDismiss={() => setFormError(null)} />}
      {serviceError && (
        <FullScreenErrorNotice message={serviceError} retryLabel="Повторить" retrying={replanMutation.isPending} onRetry={retry} />
      )}
    </>
  );
}
