import { minutesSinceMidnight, minutesToTimeLabel } from '@/lib/format';
import type { RouteStop, TicketSummary } from '@/types/domain';

interface Props {
  shiftStartMin: number;
  shiftEndMin: number;
  route: RouteStop[];
  ticketById: Map<number, TicketSummary>;
  color: string;
}

// Shows when each brigade is on-site, in transit, or free across its shift —
// answers "in which window does a ticket fall / when is the brigade idle"
// directly from the plan's own timestamps (planned_arrival, travel_time_min)
// plus duration_min/shift bounds from GET /tickets and GET /engineers.
export function EngineerTimeline({ shiftStartMin, shiftEndMin, route, ticketById, color }: Props) {
  const dayLen = shiftEndMin - shiftStartMin;
  if (dayLen <= 0) return null;

  const toPct = (min: number) => Math.min(100, Math.max(0, ((min - shiftStartMin) / dayLen) * 100));

  const segments = [...route]
    .sort((a, b) => a.sequenceNo - b.sequenceNo)
    .flatMap((stop) => {
      const ticket = ticketById.get(stop.ticketId);
      const arrivalMin = minutesSinceMidnight(stop.plannedArrival);
      const travelStart = arrivalMin - stop.travelTimeMin;
      const busyEnd = arrivalMin + (ticket?.durationMin ?? 0);
      return [
        { key: `${stop.ticketId}-travel`, start: travelStart, end: arrivalMin, color: `${color}4D` },
        { key: `${stop.ticketId}-busy`, start: arrivalMin, end: busyEnd, color }
      ];
    });

  const midLabel = minutesToTimeLabel(shiftStartMin + Math.round(dayLen / 2));

  return (
    <div>
      <div className="engineer-timeline">
        {segments.map((seg) => {
          const left = toPct(seg.start);
          const width = toPct(seg.end) - left;
          if (width <= 0) return null;
          return (
            <span
              key={seg.key}
              style={{ position: 'absolute', left: `${left.toFixed(2)}%`, width: `${width.toFixed(2)}%`, top: 0, bottom: 0, background: seg.color }}
            />
          );
        })}
      </div>
      <div className="engineer-timeline__ticks">
        <span>{minutesToTimeLabel(shiftStartMin)}</span>
        <span>{midLabel}</span>
        <span>{minutesToTimeLabel(shiftEndMin)}</span>
      </div>
    </div>
  );
}
