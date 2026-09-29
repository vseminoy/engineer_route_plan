interface Props {
  planStabilityFallback?: number;
}

// plan_stability, shown only once a plan carries a diff (after a replan):
// how many engineers' routes that event changed. PlanMetrics itself never
// carries this field — it comes from the diff, mapped separately in mapDiff.
export function OptionalMetricsBlock({ planStabilityFallback }: Props) {
  if (planStabilityFallback === undefined) return null;

  return (
    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', background: '#f4f6f8', borderRadius: 10, padding: '10px 12px' }}>
      Стабильность плана после перепланирования: <strong style={{ color: 'var(--color-text-primary)' }}>{planStabilityFallback}</strong>
    </div>
  );
}
