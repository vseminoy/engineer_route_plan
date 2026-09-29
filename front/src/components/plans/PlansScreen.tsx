import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppNav } from '@/components/common/AppNav';
import { RegionSelect } from '@/components/dataload/RegionSelect';
import { PlanDeleteConfirm } from './PlanDeleteConfirm';
import { usePlans } from '@/queries/usePlans';
import { useUiStore } from '@/store/useUiStore';
import { algorithmLabel, describeError, planStatusLabel } from '@/lib/labels';
import { formatDateTime } from '@/lib/format';
import type { PlanSummary } from '@/types/domain';

export function PlansScreen() {
  const navigate = useNavigate();
  const selectedRegion = useUiStore((s) => s.selectedRegion);
  const setSelectedRegion = useUiStore((s) => s.setSelectedRegion);
  const plansQuery = usePlans(selectedRegion);
  const [deletingPlan, setDeletingPlan] = useState<PlanSummary | null>(null);

  return (
    <div style={{ maxWidth: 640, margin: '64px auto', padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <AppNav />
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Сгенерированные планы</h1>

      <RegionSelect value={selectedRegion} onChange={setSelectedRegion} />

      {!selectedRegion && (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Выберите регион, чтобы увидеть его планы.</div>
      )}

      {selectedRegion && plansQuery.isPending && (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Загружаем список планов…</div>
      )}

      {selectedRegion && plansQuery.isError && (
        <div style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>
          {describeError(plansQuery.error, 'GET /plan')}
        </div>
      )}

      {selectedRegion && plansQuery.isSuccess && plansQuery.data.length === 0 && (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
          У этого региона ещё нет построенных планов.
        </div>
      )}

      {selectedRegion && plansQuery.isSuccess && plansQuery.data.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {plansQuery.data.map((plan) => (
            <div key={plan.planId} className="unassigned-card" onClick={() => navigate(`/plan/${plan.planId}`)}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontWeight: 600 }}>
                  План №{plan.planId}
                  {plan.parentPlanId && (
                    <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}> · от плана №{plan.parentPlanId}</span>
                  )}
                </span>
                <span className={`plan-status plan-status--${plan.status}`}>{planStatusLabel[plan.status]}</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                {algorithmLabel[plan.algorithm]} · на {plan.planDate} · построен {formatDateTime(plan.createdAt)}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn-primary"
                  style={{
                    background: 'transparent',
                    color: 'var(--color-danger-text)',
                    border: '1px solid var(--color-danger-text)',
                    padding: '6px 12px',
                    minHeight: 32,
                    fontSize: 13
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeletingPlan(plan);
                  }}
                >
                  Удалить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {deletingPlan && selectedRegion && (
        <PlanDeleteConfirm
          region={selectedRegion}
          plan={deletingPlan}
          onDeleted={() => setDeletingPlan(null)}
          onCancel={() => setDeletingPlan(null)}
        />
      )}
    </div>
  );
}
