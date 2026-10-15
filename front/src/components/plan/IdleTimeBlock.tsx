import { getEngineerColor } from '@/lib/colors';
import { formatKm, minutesToTimeLabel } from '@/lib/format';
import { SkillIcons } from './SkillIcons';
import { VehicleIcon } from './VehicleIcon';
import type { EngineerRoster, EngineerRoute } from '@/types/domain';

interface Props {
  engineers: EngineerRoute[];
  roster: EngineerRoster[];
}

// Reference-only per-brigade figures (ticket count, mileage, idle time) — never
// compared to baseline and never given a better/worse indicator, since they
// are not part of the optimizer's objective.
export function IdleTimeBlock({ engineers, roster }: Props) {
  const rosterById = new Map(roster.map((r) => [r.engineerId, r]));
  // Unused brigades sink to the bottom, greyed out — same as the earlier
  // "Не задействованы" list, just folded into one table instead of a second one.
  const sorted = [...engineers].sort((a, b) => Number(a.route.length === 0) - Number(b.route.length === 0));

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="brigade-table">
        <thead>
          <tr>
            <th aria-label="Бригада" />
            <th aria-label="Транспорт" />
            <th aria-label="Навыки" />
            <th>Смена</th>
            <th>Заявки</th>
            <th>Пробег</th>
            <th>Простой</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((e) => {
            const used = e.route.length > 0;
            const color = used ? getEngineerColor(e.engineerId) : 'var(--color-border)';
            const r = rosterById.get(e.engineerId);
            return (
              <tr key={e.engineerId} className={used ? undefined : 'brigade-table__row--idle'}>
                <td>
                  <span className="brigade-table__name">
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
                    {e.name}
                  </span>
                </td>
                <td className="brigade-table__vehicle">{r && <VehicleIcon vehicleType={r.vehicleType} />}</td>
                <td>{r && <SkillIcons skills={r.skills} />}</td>
                <td>{r && `${minutesToTimeLabel(r.shiftStartMin)}–${minutesToTimeLabel(r.shiftEndMin)}`}</td>
                <td>{e.route.length}</td>
                <td>{formatKm(e.totalDistanceKm)}</td>
                <td>{e.idleTimeMin} мин</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
