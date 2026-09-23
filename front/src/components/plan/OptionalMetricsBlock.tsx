import { getEngineerColor } from '@/lib/colors';
import type { EngineerRoute, PlanMetrics } from '@/types/domain';

interface Props {
  metrics: PlanMetrics;
  engineers: EngineerRoute[];
  planStabilityFallback?: number;
}

// 06_spec_frontend.md §3.6 — only rendered when the backend actually
// returned load_balance / plan_stability; absent fields mean the feature
// isn't enabled for this run, not zero.
export function OptionalMetricsBlock({ metrics, engineers, planStabilityFallback }: Props) {
  const planStability = metrics.planStability ?? planStabilityFallback;
  if (metrics.loadBalanceStdDev === undefined && planStability === undefined) return null;

  const maxTickets = Math.max(1, ...engineers.map((e) => e.route.length));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {metrics.loadBalanceStdDev !== undefined && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
            Балансировка загрузки (справочно)
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
                      style={{ width: `${(e.route.length / maxTickets) * 100}%`, background: color }}
                    />
                  </span>
                  <span className="bar-row__value">{e.route.length} зая.</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {planStability !== undefined && (
        <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', background: '#f4f6f8', borderRadius: 10, padding: '10px 12px' }}>
          Стабильность плана после перепланирования: <strong style={{ color: 'var(--color-text-primary)' }}>{planStability.toFixed(2)}</strong>
        </div>
      )}
    </div>
  );
}
