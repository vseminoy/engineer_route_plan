import { UnassignedTicketCard } from './UnassignedTicketCard';
import { useUiStore } from '@/store/useUiStore';
import type { DonePlan, TicketSummary } from '@/types/domain';

interface Props {
  plan: DonePlan;
  ticketById: Map<number, TicketSummary>;
}

export function UnassignedListTab({ plan, ticketById }: Props) {
  const openTicket = useUiStore((s) => s.openTicket);

  if (plan.unassigned.length === 0) {
    return <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Все заявки назначены.</div>;
  }

  return (
    <>
      {plan.unassigned.map((ticket) => (
        <UnassignedTicketCard
          key={ticket.ticketId}
          ticket={ticket}
          summary={ticketById.get(ticket.ticketId)}
          onClick={() => openTicket(ticket.ticketId)}
        />
      ))}
    </>
  );
}
