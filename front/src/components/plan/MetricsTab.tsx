import { MetricComparisonCard } from './MetricComparisonCard';
import { IdleTimeBlock } from './IdleTimeBlock';
import { OptionalMetricsBlock } from './OptionalMetricsBlock';
import { usePlanCompare } from '@/queries/usePlanCompare';
import { formatKm, formatSignedDelta } from '@/lib/format';
import { describeError } from '@/lib/labels';
import type { DonePlan, EngineerRoster } from '@/types/domain';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  engineerSetName?: string;
}

export function MetricsTab({ plan, roster, engineerSetName }: Props) {
  const compareQuery = usePlanCompare(plan.planId);
  const compare = compareQuery.data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {engineerSetName && (
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Сравнение в пределах набора «{engineerSetName}»</div>
      )}
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
      ) : compareQuery.isError ? (
        <div style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>
          {describeError(compareQuery.error, 'GET /plan/{id}/compare')}
        </div>
      ) : (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Считаем сравнение с baseline…</div>
      )}

      <IdleTimeBlock engineers={plan.engineers} roster={roster} />
      <OptionalMetricsBlock planStabilityFallback={plan.diff?.planStability} />
    </div>
  );
}
