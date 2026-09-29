import { getEngineerColor } from '@/lib/colors';
import type { EngineerRoute } from '@/types/domain';

interface Props {
  engineers: EngineerRoute[];
}

// Idle time is displayed only, never compared to baseline and never given a
// better/worse indicator — it is not part of the optimizer's objective.
export function IdleTimeBlock({ engineers }: Props) {
  const maxIdle = Math.max(1, ...engineers.map((e) => e.idleTimeMin));

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
        Простой бригад (справочно, без сравнения)
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {engineers.map((e) => {
          const color = getEngineerColor(e.engineerId);
          return (
            <div key={e.engineerId} className="bar-row">
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span className="bar-row__label">{e.name.replace('Бригада ', '')}</span>
              <span className="bar-row__track">
                <span
                  className="bar-row__fill"
                  style={{ width: `${(e.idleTimeMin / maxIdle) * 100}%`, background: color, opacity: 0.55 }}
                />
              </span>
              <span className="bar-row__value">{e.idleTimeMin} мин</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
