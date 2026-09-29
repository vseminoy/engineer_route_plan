import { getEngineerColor } from '@/lib/colors';
import { minutesToTimeLabel } from '@/lib/format';
import { SkillIcons } from './SkillIcons';
import { VehicleIcon } from './VehicleIcon';
import type { EngineerRoster, EngineerRoute } from '@/types/domain';

interface Props {
  engineers: EngineerRoute[];
  roster: EngineerRoster[];
}

// Idle time is displayed only, never compared to baseline and never given a
// better/worse indicator — it is not part of the optimizer's objective.
export function IdleTimeBlock({ engineers, roster }: Props) {
  const rosterById = new Map(roster.map((r) => [r.engineerId, r]));
  const used = engineers.filter((e) => e.route.length > 0);
  const idle = engineers.filter((e) => e.route.length === 0);
  const maxIdle = Math.max(1, ...used.map((e) => e.idleTimeMin));

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
        Простой бригад (справочно, без сравнения)
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {used.map((e) => {
          const color = getEngineerColor(e.engineerId);
          const r = rosterById.get(e.engineerId);
          return (
            <div key={e.engineerId} className="bar-row bar-row--stacked">
              <div className="bar-row__header">
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <span className="bar-row__label">{e.name}</span>
                {r && (
                  <span className="bar-row__shift">
                    {minutesToTimeLabel(r.shiftStartMin)}–{minutesToTimeLabel(r.shiftEndMin)}
                  </span>
                )}
                {r && <VehicleIcon vehicleType={r.vehicleType} />}
                {r && <SkillIcons skills={r.skills} />}
              </div>
              <div className="bar-row__body">
                <span className="bar-row__track">
                  <span
                    className="bar-row__fill"
                    style={{ width: `${(e.idleTimeMin / maxIdle) * 100}%`, background: color, opacity: 0.55 }}
                  />
                </span>
                <span className="bar-row__value">{e.idleTimeMin} мин</span>
              </div>
            </div>
          );
        })}
      </div>

      {idle.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6 }}>
            Не задействованы ({idle.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {idle.map((e) => {
              const r = rosterById.get(e.engineerId);
              return (
                <div key={e.engineerId} className="bar-row bar-row--idle">
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--color-border)', flexShrink: 0 }} />
                  <span className="bar-row__label">{e.name}</span>
                  {r && (
                    <span className="bar-row__shift">
                      {minutesToTimeLabel(r.shiftStartMin)}–{minutesToTimeLabel(r.shiftEndMin)}
                    </span>
                  )}
                  {r && <VehicleIcon vehicleType={r.vehicleType} />}
                  {r && <SkillIcons skills={r.skills} />}
                  <span className="diff-tag diff-tag--idle">не задействована</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
