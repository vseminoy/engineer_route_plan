import { Marker } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import { buildOfficeIcon } from './icons';

const officeIcon = buildOfficeIcon();

interface Props {
  position: LatLngExpression;
}

export function EngineerStartMarker({ position }: Props) {
  return <Marker position={position} icon={officeIcon} />;
}
