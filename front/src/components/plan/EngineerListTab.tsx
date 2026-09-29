import { useMemo } from 'react';
import { EngineerCard, type DiffTag } from './EngineerCard';
import { getEngineerColor } from '@/lib/colors';
import { useUiStore } from '@/store/useUiStore';
import type { DonePlan, EngineerRoster, TicketSummary } from '@/types/domain';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  ticketById: Map<number, TicketSummary>;
}

export function EngineerListTab({ plan, roster, ticketById }: Props) {
  const rosterById = useMemo(() => new Map(roster.map((r) => [r.engineerId, r])), [roster]);
  const highlightedEngineerId = useUiStore((s) => s.highlightedEngineerId);
  const toggleHighlightedEngineer = useUiStore((s) => s.toggleHighlightedEngineer);
  const openTicket = useUiStore((s) => s.openTicket);

  const diffTagsByTicket = useMemo(() => {
    const map = new Map<number, DiffTag>();
    if (plan.diff) {
      plan.diff.newlyAssigned.forEach((id) => map.set(id, 'new'));
      plan.diff.changedAssignments.forEach((c) => {
        if (!map.has(c.ticketId)) map.set(c.ticketId, 'changed');
      });
    }
    return map;
  }, [plan.diff]);

  return (
    <>
      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', padding: '0 2px 2px' }}>
        Шкала смены · тёмный — на объекте, светлый — в пути, серый — бригада свободна
      </div>
      {plan.engineers
        .filter((engineer) => engineer.route.length > 0)
        .map((engineer) => (
          <EngineerCard
            key={engineer.engineerId}
            engineer={engineer}
            roster={rosterById.get(engineer.engineerId)}
            color={getEngineerColor(engineer.engineerId)}
            ticketById={ticketById}
            diffTags={diffTagsByTicket}
            selected={highlightedEngineerId === engineer.engineerId}
            onSelect={() => toggleHighlightedEngineer(engineer.engineerId)}
            onStopClick={openTicket}
          />
        ))}
    </>
  );
}
