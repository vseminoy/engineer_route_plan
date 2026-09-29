interface Props {
  label: string;
  mainValue: string;
  baselineValue: string;
  deltaLabel: string;
  good: boolean;
}

// Main plan vs baseline, with an explicit delta and an improvement/regression
// indicator — never color alone: the arrow direction and text carry the
// meaning too.
export function MetricComparisonCard({ label, mainValue, baselineValue, deltaLabel, good }: Props) {
  return (
    <div className="metric-card">
      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span className="metric-card__value">{mainValue}</span>
        <span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>baseline: {baselineValue}</span>
      </div>
      <div className={`metric-delta ${good ? 'metric-delta--good' : 'metric-delta--bad'}`}>
        <svg width={10} height={10} viewBox="0 0 10 10">
          <path
            d={good ? 'M5,1 L5,8 M2,5 L5,8 L8,5' : 'M5,9 L5,2 M2,5 L5,2 L8,5'}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.4}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {deltaLabel}
      </div>
    </div>
  );
}
