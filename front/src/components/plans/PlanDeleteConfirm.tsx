import { useState } from 'react';
import { useDeletePlan } from '@/queries/useDeletePlan';
import { describeError } from '@/lib/labels';
import type { PlanSummary, RegionCode } from '@/types/domain';

interface Props {
  region: RegionCode;
  plan: PlanSummary;
  onDeleted: () => void;
  onCancel: () => void;
}

export function PlanDeleteConfirm({ region, plan, onDeleted, onCancel }: Props) {
  const deleteMutation = useDeletePlan(region);
  const [error, setError] = useState<string | null>(null);

  function handleConfirm() {
    setError(null);
    deleteMutation.mutate(plan.planId, {
      onSuccess: onDeleted,
      onError: (err) => setError(describeError(err, 'DELETE /plan/{id}'))
    });
  }

  return (
    <div className="ticket-modal__overlay" role="dialog" aria-modal="true">
      <div className="ticket-modal__card" style={{ width: 380, gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>Удалить план №{plan.planId}?</h2>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--color-text-secondary)' }}>
          Все перепланирования, сделанные от этого плана, тоже будут удалены.
        </p>
        {error && <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{error}</span>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn-primary"
            style={{ background: 'var(--color-danger-text)' }}
            onClick={handleConfirm}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Удаляем…' : 'Удалить'}
          </button>
          <button
            type="button"
            className="btn-primary"
            style={{ background: 'transparent', color: 'var(--color-text-primary)', border: '1px solid rgba(18,21,26,0.14)' }}
            onClick={onCancel}
            disabled={deleteMutation.isPending}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
