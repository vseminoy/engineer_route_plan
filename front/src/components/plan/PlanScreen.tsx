import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MapView } from '@/components/map/MapView';
import { SidePanel } from './SidePanel';
import { DiffBanner } from './DiffBanner';
import { TicketExplanationModal } from '@/components/ticket/TicketExplanationModal';
import { LoadingOverlay } from '@/components/common/LoadingOverlay';
import { ErrorToast } from '@/components/common/ErrorToast';
import { FullScreenErrorNotice } from '@/components/common/FullScreenErrorNotice';
import { usePlan } from '@/queries/usePlan';
import { useEngineers } from '@/queries/useEngineers';
import { useEngineerSets } from '@/queries/useEngineerSets';
import { useTickets } from '@/queries/useTickets';
import { useUiStore } from '@/store/useUiStore';
import { describeError, planFailedReasonText } from '@/lib/labels';
import { PLAN_DATE } from '@/lib/planDate';
import { buildPlan } from '@/api/endpoints';
import { ApiError } from '@/api/client';
import type { DonePlan } from '@/types/domain';

export function PlanScreen() {
  const { planId: planIdParam } = useParams<{ planId: string }>();
  const planId = Number(planIdParam);
  const navigate = useNavigate();
  const selectedRegion = useUiStore((s) => s.selectedRegion);
  const selectedTicketId = useUiStore((s) => s.selectedTicketId);
  const closeTicket = useUiStore((s) => s.closeTicket);
  const [dismissedError, setDismissedError] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildError, setRebuildError] = useState<string | null>(null);

  const planQuery = usePlan(planId);
  const engineersQuery = useEngineers(selectedRegion, planQuery.data?.engineerSetId ?? null);
  const ticketsQuery = useTickets(selectedRegion);
  const engineerSetsQuery = useEngineerSets(selectedRegion);

  const ticketById = useMemo(
    () => new Map((ticketsQuery.data ?? []).map((t) => [t.ticketId, t])),
    [ticketsQuery.data]
  );

  const engineerSetName = engineerSetsQuery.data?.find((s) => s.id === planQuery.data?.engineerSetId)?.name;

  async function rebuild(algorithm: 'or_tools' | 'baseline_fcfs', engineerSetId: number) {
    if (!selectedRegion) return;
    setRebuildError(null);
    setRebuilding(true);
    try {
      const rebuilt = await buildPlan(selectedRegion, PLAN_DATE, algorithm, engineerSetId);
      navigate(`/plan/${rebuilt.planId}`);
    } catch (err) {
      setRebuildError(describeError(err, 'POST /plan/build'));
      setRebuilding(false);
    }
  }

  if (planQuery.isPending) return <LoadingOverlay text="Строим план…" />;

  if (planQuery.isError) {
    const message = describeError(planQuery.error, 'GET /plan/{id}');
    if (planQuery.error instanceof ApiError && (planQuery.error.status === 503 || planQuery.error.status === 500)) {
      return (
        <FullScreenErrorNotice
          message={message}
          retryLabel="Повторить"
          retrying={planQuery.isFetching}
          onRetry={() => planQuery.refetch()}
        />
      );
    }
    return <LoadingOverlay text={message} />;
  }

  const plan = planQuery.data;

  // The build hasn't finished yet: poll (usePlan's
  // refetchInterval) instead of showing the map/tabs.
  if (plan.status === 'running') {
    return <LoadingOverlay text="Подождите, идёт расчёт…" />;
  }

  if (plan.status === 'failed') {
    const reason = plan.failedReason ? planFailedReasonText[plan.failedReason] : 'Не удалось построить план';
    return (
      <FullScreenErrorNotice
        message={rebuildError ?? reason}
        retryLabel="Построить заново"
        retrying={rebuilding}
        onRetry={() => rebuild(plan.algorithm, plan.engineerSetId)}
      />
    );
  }

  const donePlan: DonePlan = {
    planId: plan.planId,
    algorithm: plan.algorithm,
    engineerSetId: plan.engineerSetId,
    parentPlanId: plan.parentPlanId,
    engineers: plan.engineers ?? [],
    unassigned: plan.unassigned ?? [],
    metrics: plan.metrics ?? {
      engineersUsed: 0,
      totalDistanceKm: 0,
      distanceByEngineer: {},
      assignedCount: 0,
      unassignedCount: 0,
      idleTimeByEngineerMin: {}
    },
    diff: plan.diff
  };

  return (
    <div className="plan-screen">
      <div className="plan-screen__header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>
            Диспетчер{selectedRegion ? ` · ${selectedRegion}` : ''}
            {engineerSetName ? ` · ${engineerSetName}` : ''}
          </h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          <span>Бригад в плане: {donePlan.engineers.length}</span>
          <span>Не назначено: {donePlan.unassigned.length}</span>
        </div>
      </div>

      <div className="plan-screen__body">
        <div className="plan-screen__map-column">
          <DiffBanner plan={donePlan} ticketById={ticketById} />
          <div className="plan-screen__map-surface">
            <MapView plan={donePlan} roster={engineersQuery.data ?? []} tickets={ticketsQuery.data ?? []} />
          </div>
        </div>

        <SidePanel
          plan={donePlan}
          roster={engineersQuery.data ?? []}
          ticketById={ticketById}
          engineerSetName={engineerSetName}
          onReplanned={(newPlanId) => navigate(`/plan/${newPlanId}`)}
        />
      </div>

      {selectedTicketId !== null && (
        <TicketExplanationModal
          plan={donePlan}
          ticketById={ticketById}
          ticketId={selectedTicketId}
          region={selectedRegion}
          onClose={closeTicket}
        />
      )}

      {(engineersQuery.isError || ticketsQuery.isError) && !dismissedError && (
        <ErrorToast message="Не удалось загрузить часть данных бригад/заявок." onDismiss={() => setDismissedError(true)} />
      )}
    </div>
  );
}
