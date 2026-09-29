import { useRegions } from '@/queries/useRegions';
import type { RegionCode } from '@/types/domain';

const FALLBACK_REGIONS: Array<{ code: RegionCode; name: string }> = [
  { code: 'east', name: 'Восток' },
  { code: 'south_east', name: 'Юго-Восток' },
  { code: 'south_center', name: 'Югоцентр' }
];

interface Props {
  value: RegionCode | null;
  onChange: (region: RegionCode) => void;
  onBlur?: () => void;
  error?: string;
}

export function RegionSelect({ value, onChange, onBlur, error }: Props) {
  const regionsQuery = useRegions();
  const regions = regionsQuery.data && regionsQuery.data.length > 0 ? regionsQuery.data : FALLBACK_REGIONS;

  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--color-text-secondary)' }}>
      Регион
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value as RegionCode)}
        onBlur={onBlur}
        style={{ fontSize: 15, padding: '10px 12px', minHeight: 44, borderRadius: 8, border: '1px solid rgba(18,21,26,0.14)' }}
      >
        <option value="" disabled>
          Выберите регион…
        </option>
        {regions.map((r) => (
          <option key={r.code} value={r.code}>
            {r.name}
          </option>
        ))}
      </select>
      {error && <span style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{error}</span>}
    </label>
  );
}
