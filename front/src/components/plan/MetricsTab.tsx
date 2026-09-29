import { MetricComparisonCard } from './MetricComparisonCard';
import { IdleTimeBlock } from './IdleTimeBlock';
import { OptionalMetricsBlock } from './OptionalMetricsBlock';
import { usePlanCompare } from '@/queries/usePlanCompare';
import { formatKm, formatSignedDelta } from '@/lib/format';
import type { DonePlan } from '@/types/domain';

interface Props {
  plan: DonePlan;
}

export function MetricsTab({ plan }: Props) {
  const compare = usePlanCompare(plan.planId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {compare ? (
        <>
          <MetricComparisonCard
            label="Задействовано исполнителей"
            mainValue={String(compare.engineersUsed.main)}
            baselineValue={String(compare.engineersUsed.baseline)}
            deltaLabel={formatSignedDelta(compare.engineersUsed.delta, (v) => String(v))}
            good={compare.engineersUsed.delta <= 0}
          />
          <MetricComparisonCard
            label="Суммарный пробег"
            mainValue={formatKm(compare.totalDistanceKm.main)}
            baselineValue={formatKm(compare.totalDistanceKm.baseline)}
            deltaLabel={formatSignedDelta(compare.totalDistanceKm.delta, formatKm)}
            good={compare.totalDistanceKm.delta <= 0}
          />
        </>
      ) : (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Считаем сравнение с baseline…</div>
      )}

      <IdleTimeBlock engineers={plan.engineers} />
      <OptionalMetricsBlock metrics={plan.metrics} engineers={plan.engineers} planStabilityFallback={plan.diff?.planStability} />
    </div>
  );
}
