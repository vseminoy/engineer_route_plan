interface Props {
  planStabilityFallback?: number;
}

// 06_spec_frontend.md §3.6 — plan_stability, shown only once a plan carries a
// diff (i.e. after a replan, F6): how many engineers' routes that event
// changed. PlanMetrics itself never carries load-balance/stability fields —
// specs/openapi.yaml only ever returns the fixed set mapped in
// mapPlanMetrics (api/mappers.ts).
export function OptionalMetricsBlock({ planStabilityFallback }: Props) {
  if (planStabilityFallback === undefined) return null;

  return (
    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', background: '#f4f6f8', borderRadius: 10, padding: '10px 12px' }}>
      Стабильность плана после перепланирования: <strong style={{ color: 'var(--color-text-primary)' }}>{planStabilityFallback}</strong>
    </div>
  );
}
