import { useState } from 'react';
import { useCreateEngineerSet } from '@/queries/useCreateEngineerSet';
import { CreateEngineerSetBody } from '@/api/generated/zod/engineerRoutePlanAPI';
import { ApiError } from '@/api/client';
import { describeError } from '@/lib/labels';
import { fieldErrorsFromApi, fieldErrorsFromZod, isFieldErrors, type FieldErrorMap } from '@/lib/fieldErrors';
import type { EngineerSet, RegionCode } from '@/types/domain';

interface Props {
  region: RegionCode;
  onCreated: (set: EngineerSet) => void;
  onCancel: () => void;
}

const ENDPOINT = 'POST /engineer-sets';
const fieldLabelStyle = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' } as const;
const fieldErrorStyle = { fontSize: 13, color: 'var(--color-danger-text)' } as const;

export function EngineerSetCreateForm({ region, onCreated, onCancel }: Props) {
  const [name, setName] = useState('');
  const [engineers, setEngineers] = useState('10');
  const [morningShare, setMorningShare] = useState('0.5');
  const [eveningShare, setEveningShare] = useState('0.5');
  const [seed, setSeed] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrorMap>({});
  const [formError, setFormError] = useState<string | null>(null);
  const createMutation = useCreateEngineerSet(region);

  function handleSubmit() {
    setFormError(null);
    const request = {
      region,
      name,
      engineers: Number(engineers),
      morning_share: Number(morningShare),
      evening_share: Number(eveningShare),
      seed
    };
    const parsed = CreateEngineerSetBody.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setFieldErrors({});
    createMutation.mutate(parsed.data, {
      onSuccess: (set) => onCreated(set),
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
    });
  }

  return (
    <div className="ticket-modal__overlay" role="dialog" aria-modal="true">
      <div className="ticket-modal__card" style={{ width: 420 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Новый набор бригад</h2>

        <label style={fieldLabelStyle}>
          Название
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например, 13 бригад" />
        </label>
        {fieldErrors.name && <span style={fieldErrorStyle}>{fieldErrors.name}</span>}

        <label style={fieldLabelStyle}>
          Число бригад
          <input type="number" min={1} max={30} value={engineers} onChange={(e) => setEngineers(e.target.value)} />
        </label>
        {fieldErrors.engineers && <span style={fieldErrorStyle}>{fieldErrors.engineers}</span>}

        <div style={{ display: 'flex', gap: 8 }}>
          <label style={{ ...fieldLabelStyle, flex: 1 }}>
            Доля утренней смены
            <input type="number" step="0.1" min={0} max={1} value={morningShare} onChange={(e) => setMorningShare(e.target.value)} />
          </label>
          <label style={{ ...fieldLabelStyle, flex: 1 }}>
            Доля вечерней смены
            <input type="number" step="0.1" min={0} max={1} value={eveningShare} onChange={(e) => setEveningShare(e.target.value)} />
          </label>
        </div>
        {(fieldErrors.morning_share || fieldErrors.evening_share) && (
          <span style={fieldErrorStyle}>{fieldErrors.morning_share ?? fieldErrors.evening_share}</span>
        )}

        <label style={fieldLabelStyle}>
          Зерно генератора (seed)
          <input type="text" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="Например, demo-13" />
        </label>
        {fieldErrors.seed && <span style={fieldErrorStyle}>{fieldErrors.seed}</span>}

        {formError && <span style={fieldErrorStyle}>{formError}</span>}

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={handleSubmit} disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Создаём…' : 'Создать'}
          </button>
          <button
            type="button"
            className="btn-primary"
            style={{ background: 'transparent', color: 'var(--color-text-primary)', border: '1px solid rgba(18,21,26,0.14)' }}
            onClick={onCancel}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
