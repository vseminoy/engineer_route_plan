import { Polyline } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';

interface Props {
  positions: LatLngExpression[];
  color: string;
  selected: boolean;
  dimmed: boolean;
  diffActive: boolean;
  onClick: () => void;
}

export function EngineerRouteLayer({ positions, color, selected, dimmed, diffActive, onClick }: Props) {
  if (positions.length < 2) return null;
  return (
    <Polyline
      positions={positions}
      eventHandlers={{ click: onClick }}
      pathOptions={{
        color,
        weight: selected ? 5 : 3,
        opacity: dimmed ? 0.25 : 1,
        dashArray: diffActive ? '10,6' : undefined,
        lineCap: 'round',
        lineJoin: 'round'
      }}
    />
  );
}
