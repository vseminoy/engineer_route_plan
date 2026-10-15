interface Props {
  label: string;
  mainValue: string;
  baselineValue: string;
  deltaLabel: string;
  good: boolean;
}

// One compact row inside the `.metrics-compare` grid (main plan vs baseline),
// with an explicit delta and an improvement/regression indicator — never
// color alone: the arrow direction and text carry the meaning too.
// `metric-row` is `display: contents` so label/value/delta become direct
// grid items of the parent, letting all rows' values and deltas align in
// columns.
export function MetricComparisonCard({ label, mainValue, baselineValue, deltaLabel, good }: Props) {
  return (
    <div className="metric-row">
      <span className="metric-row__label">{label}</span>
      <span className="metric-row__value">
        {mainValue}
        <span className="metric-row__baseline">baseline: {baselineValue}</span>
      </span>
      <span className={`metric-delta ${good ? 'metric-delta--good' : 'metric-delta--bad'}`}>
        <svg width={9} height={9} viewBox="0 0 10 10">
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
      </span>
    </div>
  );
}
