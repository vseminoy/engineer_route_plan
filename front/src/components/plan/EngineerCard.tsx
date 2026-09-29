import { SkillIcons } from './SkillIcons';
import { VehicleIcon } from './VehicleIcon';
import { EngineerTimeline } from './EngineerTimeline';
import { formatKm, formatMinutes, minutesToTimeLabel, timeOnly } from '@/lib/format';
import type { EngineerRoster, EngineerRoute, TicketSummary } from '@/types/domain';

export type DiffTag = 'new' | 'changed';

interface Props {
  engineer: EngineerRoute;
  roster: EngineerRoster | undefined;
  color: string;
  ticketById: Map<number, TicketSummary>;
  diffTags: Map<number, DiffTag>;
  selected: boolean;
  onSelect: () => void;
  onStopClick: (ticketId: number) => void;
}

export function EngineerCard({ engineer, roster, color, ticketById, diffTags, selected, onSelect, onStopClick }: Props) {
  const stops = [...engineer.route].sort((a, b) => a.sequenceNo - b.sequenceNo);
  const totalTimeMin = engineer.totalTravelTimeMin + stops.reduce((sum, s) => sum + (ticketById.get(s.ticketId)?.durationMin ?? 0), 0);

  return (
    <div
      className={`engineer-card${selected ? ' engineer-card--selected' : ''}`}
      style={{ ['--engineer-color' as string]: color }}
      onClick={onSelect}
    >
      <div className="engineer-card__header">
        <span className="engineer-card__dot" style={{ background: color }} />
        <span className="engineer-card__name">{engineer.name}</span>
        {roster && <VehicleIcon vehicleType={roster.vehicleType} />}
        {roster && <SkillIcons skills={roster.skills} />}
      </div>
      <div className="engineer-card__meta">
        {stops.length} заявки · {formatMinutes(totalTimeMin)} · {formatKm(engineer.totalDistanceKm)}
      </div>

      {roster && (
        <EngineerTimeline
          shiftStartMin={roster.shiftStartMin}
          shiftEndMin={roster.shiftEndMin}
          route={engineer.route}
          ticketById={ticketById}
          color={color}
        />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 2, borderTop: '1px solid rgba(18,21,26,0.06)', paddingTop: 8 }}>
        {stops.map((stop) => {
          const ticket = ticketById.get(stop.ticketId);
          const tag = diffTags.get(stop.ticketId);
          return (
            <div
              key={stop.ticketId}
              className="stop-row"
              onClick={(e) => {
                e.stopPropagation();
                onStopClick(stop.ticketId);
              }}
            >
              <div className="stop-row__main">
                <span className="stop-row__eta">{timeOnly(stop.plannedArrival)}</span>
                <span>{ticket?.address ?? `Заявка №${stop.ticketId}`}</span>
                {tag && (
                  <span className={`diff-tag diff-tag--${tag}`}>{tag === 'new' ? 'новое' : 'время изменилось'}</span>
                )}
              </div>
              {ticket && (
                <div className="stop-row__window">
                  окно {minutesToTimeLabel(ticket.windowStartMin)}–{minutesToTimeLabel(ticket.windowEndMin)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
