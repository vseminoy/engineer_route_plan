import { useEngineerSets } from '@/queries/useEngineerSets';
import type { EngineerSet, RegionCode } from '@/types/domain';

interface Props {
  region: RegionCode | null;
  value: number | null; // null — the region's default set
  onChange: (engineerSetId: number | null) => void;
  onCreateClick: () => void;
  onDeleteClick: (engineerSet: EngineerSet) => void;
  disabled?: boolean;
}

// The default set always maps to '' (the domain's `null`), whatever its own
// server id — an id it does have, but the dispatcher never needs it, and
// POST /plan/build treats null the same as passing that id explicitly.
export function EngineerSetSelect({ region, value, onChange, onCreateClick, onDeleteClick, disabled }: Props) {
  const setsQuery = useEngineerSets(region);
  const sets = setsQuery.data ?? [];
  const selected = sets.find((s) => s.id === value);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--color-text-secondary)' }}>
        Набор бригад
        <select
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          disabled={disabled || !region || sets.length === 0}
          style={{ fontSize: 15, padding: '10px 12px', minHeight: 44, borderRadius: 8, border: '1px solid rgba(18,21,26,0.14)' }}
        >
          {sets.length === 0 && (
            <option value="" disabled>
              Нет наборов — сначала загрузите данные региона
            </option>
          )}
          {sets.map((s) => (
            <option key={s.id} value={s.kind === 'demo' ? '' : s.id}>
              {s.kind === 'demo' ? 'По умолчанию' : `${s.name} — ${s.description}`}
            </option>
          ))}
        </select>
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          className="btn-primary"
          style={{ background: 'transparent', color: 'var(--color-text-primary)', border: '1px solid rgba(18,21,26,0.14)' }}
          disabled={disabled || !region}
          onClick={onCreateClick}
        >
          + Новый набор
        </button>
        {selected && selected.kind === 'generated' && (
          <button
            type="button"
            className="btn-primary"
            style={{ background: 'transparent', color: 'var(--color-danger-text)', border: '1px solid var(--color-danger-text)' }}
            disabled={disabled}
            onClick={() => onDeleteClick(selected)}
          >
            Удалить набор
          </button>
        )}
      </div>
    </div>
  );
}
