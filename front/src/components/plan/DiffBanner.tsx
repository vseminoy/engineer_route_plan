import { useUiStore } from '@/store/useUiStore';
import { timeOnly } from '@/lib/format';
import type { Plan, TicketSummary } from '@/types/domain';

interface Props {
  plan: Plan;
  ticketById: Map<number, TicketSummary>;
}

// FR-16/FR-22 — a short "Изменено назначений: N" banner with an expandable
// details list (before → after / new), per 06_spec_frontend.md §3.8.
export function DiffBanner({ plan, ticketById }: Props) {
  const diffDetailsOpen = useUiStore((s) => s.diffDetailsOpen);
  const toggleDiffDetails = useUiStore((s) => s.toggleDiffDetails);

  if (!plan.diff) return null;
  const { diff } = plan;

  const engineerNameById = new Map(plan.engineers.map((e) => [e.engineerId, e.name]));
  const engineerRouteArrival = (engineerId: number, ticketId: number) =>
    engineerNameById.has(engineerId)
      ? timeOnly(plan.engineers.find((e) => e.engineerId === engineerId)?.route.find((s) => s.ticketId === ticketId)?.plannedArrival ?? '')
      : '';

  const changedRows = diff.changedAssignments.map((c) => ({
    key: `changed-${c.ticketId}`,
    isNew: false,
    address: ticketById.get(c.ticketId)?.address ?? `Заявка №${c.ticketId}`,
    detail:
      c.beforeEngineerId !== undefined && c.afterEngineerId !== undefined
        ? `было: ${engineerNameById.get(c.beforeEngineerId) ?? c.beforeEngineerId} → стало: ${
            engineerNameById.get(c.afterEngineerId) ?? c.afterEngineerId
          }, ${engineerRouteArrival(c.afterEngineerId, c.ticketId)}`
        : 'изменена последовательность визита'
  }));

  const newRows = diff.newlyAssigned.map((ticketId) => {
    const engineer = plan.engineers.find((e) => e.route.some((s) => s.ticketId === ticketId));
    return {
      key: `new-${ticketId}`,
      isNew: true,
      address: ticketById.get(ticketId)?.address ?? `Заявка №${ticketId}`,
      detail: engineer ? `→ ${engineer.name}, ${engineerRouteArrival(engineer.engineerId, ticketId)}` : '→ назначена'
    };
  });

  const rows = [...newRows, ...changedRows];
  if (rows.length === 0) return null;

  return (
    <div className="diff-banner">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ fontSize: 14 }}>
          План перестроен. Изменено назначений: <strong>{rows.length}</strong>
        </span>
        <button
          onClick={toggleDiffDetails}
          style={{ background: 'none', border: 'none', color: 'var(--color-accent)', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
        >
          {diffDetailsOpen ? 'Скрыть детали' : 'Показать детали'}
        </button>
      </div>
      {diffDetailsOpen && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, borderTop: '1px solid #BBD6F2', paddingTop: 10 }}>
          {rows.map((row) => (
            <div key={row.key} style={{ fontSize: 13, display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
              <span className={`diff-tag diff-tag--${row.isNew ? 'new' : 'changed'}`}>{row.isNew ? 'Новое' : 'Изменено'}</span>
              <span style={{ fontWeight: 500 }}>{row.address}</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>{row.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
