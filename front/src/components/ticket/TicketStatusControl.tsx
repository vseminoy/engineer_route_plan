import { useEffect, useState } from 'react';
import { ticketStatusLabel } from '@/lib/labels';
import { allowedNextStatuses } from '@/lib/ticketStatus';
import type { TicketStatus } from '@/types/domain';

interface Props {
  status: TicketStatus;
  pending: boolean;
  error?: string | null;
  onChange: (next: TicketStatus) => void;
}

// Дежурный меняет статус заявки по сообщению бригады — сама заявка не
// умеет ни отправлять, ни принимать эти сообщения автоматически.
export function TicketStatusControl({ status, pending, error, onChange }: Props) {
  const options = allowedNextStatuses(status);
  const [selected, setSelected] = useState<TicketStatus | ''>('');

  // A successful change moves `status` forward — drop the stale selection
  // instead of leaving a picked option that no longer applies.
  useEffect(() => setSelected(''), [status]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 14, color: 'var(--color-text-secondary)' }}>
        Статус: <strong style={{ color: 'var(--color-text-primary)' }}>{ticketStatusLabel[status]}</strong>
      </div>

      {options.length > 0 ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <select
            aria-label="Новый статус заявки"
            value={selected}
            disabled={pending}
            onChange={(e) => setSelected(e.target.value as TicketStatus)}
            style={{ fontSize: 14, padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(18,21,26,0.14)' }}
          >
            <option value="" disabled>
              Изменить статус…
            </option>
            {options.map((s) => (
              <option key={s} value={s}>
                {ticketStatusLabel[s]}
              </option>
            ))}
          </select>
          <button
            className="btn-primary"
            disabled={pending || !selected}
            onClick={() => selected && onChange(selected)}
          >
            {pending ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Статус закрыт, изменить нельзя.</div>
      )}

      {error && <div style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{error}</div>}
    </div>
  );
}
