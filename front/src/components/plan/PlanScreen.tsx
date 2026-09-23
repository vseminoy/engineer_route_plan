import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MapView } from '@/components/map/MapView';
import { SidePanel } from './SidePanel';
import { DiffBanner } from './DiffBanner';
import { TicketExplanationModal } from '@/components/ticket/TicketExplanationModal';
import { LoadingOverlay } from '@/components/common/LoadingOverlay';
import { ErrorToast } from '@/components/common/ErrorToast';
import { usePlan } from '@/queries/usePlan';
import { useEngineers } from '@/queries/useEngineers';
import { useTickets } from '@/queries/useTickets';
import { useUiStore } from '@/store/useUiStore';
import { describeApiError } from '@/lib/labels';
import { ApiError } from '@/api/client';

export function PlanScreen() {
  const { planId: planIdParam } = useParams<{ planId: string }>();
  const planId = Number(planIdParam);
  const navigate = useNavigate();
  const selectedRegion = useUiStore((s) => s.selectedRegion);
  const selectedTicketId = useUiStore((s) => s.selectedTicketId);
  const closeTicket = useUiStore((s) => s.closeTicket);
  const [dismissedError, setDismissedError] = useState(false);

  const planQuery = usePlan(planId);
  const engineersQuery = useEngineers(selectedRegion);
  const ticketsQuery = useTickets(selectedRegion, planId);

  const ticketById = useMemo(
    () => new Map((ticketsQuery.data ?? []).map((t) => [t.ticketId, t])),
    [ticketsQuery.data]
  );

  if (planQuery.isPending) return <LoadingOverlay text="Строим план…" />;

  if (planQuery.isError) {
    const message =
      planQuery.error instanceof ApiError
        ? describeApiError(planQuery.error.errorCode, planQuery.error.message)
        : 'Не удалось загрузить план.';
    if (planQuery.error instanceof ApiError && planQuery.error.errorCode === 'OSRM_UNAVAILABLE') {
      return (
        <LoadingOverlay text={`${message} Попробуйте обновить страницу.`} />
      );
    }
    return <LoadingOverlay text={message} />;
  }

  const plan = planQuery.data;

  return (
    <div className="plan-screen">
      <div className="plan-screen__header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>Диспетчер{selectedRegion ? ` · ${selectedRegion}` : ''}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          <span>Бригад в плане: {plan.engineers.length}</span>
          <span>Не назначено: {plan.unassigned.length}</span>
        </div>
      </div>

      <div className="plan-screen__body">
        <div className="plan-screen__map-column">
          <DiffBanner plan={plan} ticketById={ticketById} />
          <div className="plan-screen__map-surface">
            <MapView plan={plan} roster={engineersQuery.data ?? []} tickets={ticketsQuery.data ?? []} />
          </div>
        </div>

        <SidePanel
          plan={plan}
          roster={engineersQuery.data ?? []}
          ticketById={ticketById}
          onReplanned={(newPlanId) => navigate(`/plan/${newPlanId}`)}
        />
      </div>

      {selectedTicketId !== null && (
        <TicketExplanationModal plan={plan} ticketById={ticketById} ticketId={selectedTicketId} onClose={closeTicket} />
      )}

      {(engineersQuery.isError || ticketsQuery.isError) && !dismissedError && (
        <ErrorToast message="Не удалось загрузить часть данных бригад/заявок." onDismiss={() => setDismissedError(true)} />
      )}
    </div>
  );
}
