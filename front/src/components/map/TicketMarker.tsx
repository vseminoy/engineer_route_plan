import { Marker } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import { buildTicketIcon } from './icons';
import type { TicketStatus } from '@/types/domain';

interface Props {
  position: LatLngExpression;
  color: string;
  urgent: boolean;
  emergency: boolean;
  unassigned: boolean;
  status: TicketStatus;
  diffHighlight?: boolean;
  selected?: boolean;
  opacity?: number;
  onClick: () => void;
}

export function TicketMarker({ position, color, urgent, emergency, unassigned, status, diffHighlight, selected, opacity, onClick }: Props) {
  return (
    <Marker
      position={position}
      icon={buildTicketIcon({ color, urgent, emergency, unassigned, status, diffHighlight, selected })}
      opacity={opacity ?? 1}
      zIndexOffset={selected ? 1000 : 0}
      eventHandlers={{ click: onClick }}
    />
  );
}
