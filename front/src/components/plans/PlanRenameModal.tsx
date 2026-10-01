import { useState } from 'react';
import { useRenamePlan } from '@/queries/useRenamePlan';
import { RenamePlanBody } from '@/api/generated/zod/engineerRoutePlanAPI';
import { ApiError } from '@/api/client';
import { describeError } from '@/lib/labels';
import { fieldErrorsFromApi, fieldErrorsFromZod, isFieldErrors, type FieldErrorMap } from '@/lib/fieldErrors';
import type { PlanSummary, RegionCode } from '@/types/domain';

interface Props {
  region: RegionCode;
  plan: PlanSummary;
  onRenamed: (summary: PlanSummary) => void;
  onCancel: () => void;
}

const ENDPOINT = 'PATCH /plan/{id}';

export function PlanRenameModal({ region, plan, onRenamed, onCancel }: Props) {
  const [name, setName] = useState(plan.name);
  const [fieldErrors, setFieldErrors] = useState<FieldErrorMap>({});
  const [formError, setFormError] = useState<string | null>(null);
  const renameMutation = useRenamePlan(region);

  function handleSubmit() {
    setFormError(null);
    // Trimmed before validation: the spec's minLength counts raw characters, so a
    // whitespace-only name would otherwise pass zod and only be rejected server-side.
    const parsed = RenamePlanBody.safeParse({ name: name.trim() });
    if (!parsed.success) {
      setFieldErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setFieldErrors({});
    renameMutation.mutate(
      { planId: plan.planId, name: parsed.data.name },
      {
        onSuccess: (summary) => onRenamed(summary),
        onError: (err) => {
          if (err instanceof ApiError && err.status === 400 && err.body) {
            const body = err.body;
            if (isFieldErrors(body)) {
              setFieldErrors(fieldErrorsFromApi(body));
            } else {
              setFormError(body.message);
            }
            return;
          }
          setFormError(describeError(err, ENDPOINT));
        }
      }
    );
  }

  return (
    <div className="ticket-modal__overlay" role="dialog" aria-modal="true">
      <div className="ticket-modal__card" style={{ width: 380, gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>Переименовать план №{plan.planId}</h2>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
          Название
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {fieldErrors.name && <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{fieldErrors.name}</span>}
        {formError && <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{formError}</span>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={handleSubmit} disabled={renameMutation.isPending}>
            {renameMutation.isPending ? 'Сохраняем…' : 'Переименовать'}
          </button>
          <button
            type="button"
            className="btn-primary"
            style={{ background: 'transparent', color: 'var(--color-text-primary)', border: '1px solid rgba(18,21,26,0.14)' }}
            onClick={onCancel}
            disabled={renameMutation.isPending}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
