import { Marker } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import { buildTicketIcon } from './icons';

interface Props {
  position: LatLngExpression;
  color: string;
  urgent: boolean;
  emergency: boolean;
  unassigned: boolean;
  diffHighlight?: boolean;
  opacity?: number;
  onClick: () => void;
}

export function TicketMarker({ position, color, urgent, emergency, unassigned, diffHighlight, opacity, onClick }: Props) {
  return (
    <Marker
      position={position}
      icon={buildTicketIcon({ color, urgent, emergency, unassigned, diffHighlight })}
      opacity={opacity ?? 1}
      eventHandlers={{ click: onClick }}
    />
  );
}
