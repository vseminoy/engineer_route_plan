import { vehicleLabel } from '@/lib/labels';
import type { VehicleType } from '@/types/domain';

const ICON_PATH: Record<VehicleType, JSX.Element> = {
  car: (
    <>
      <path
        d="M4,13 L5,8 C5.3,7 6,6.5 7,6.5 L13,6.5 C14,6.5 14.7,7 15,8 L16,13"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinejoin="round"
      />
      <rect x={3} y={13} width={14} height={3.5} rx={1.2} fill="none" stroke="currentColor" strokeWidth={1.6} />
      <circle cx={6.5} cy={16.5} r={1.4} fill="currentColor" />
      <circle cx={13.5} cy={16.5} r={1.4} fill="currentColor" />
    </>
  ),
  foot: (
    <>
      <circle cx={10} cy={4.5} r={2} fill="currentColor" />
      <path
        d="M10,7 L10,12 M10,12 L6,17 M10,12 L14,15 M7,10 L4,12 M13,10 L16,9"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </>
  ),
  bike: (
    <>
      <circle cx={5.5} cy={14} r={3} fill="none" stroke="currentColor" strokeWidth={1.5} />
      <circle cx={14.5} cy={14} r={3} fill="none" stroke="currentColor" strokeWidth={1.5} />
      <path
        d="M5.5,14 L9,7 L13,7 M9,7 L11,11 L14.5,14 M11,11 L7,11"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </>
  ),
  public_transport: (
    <>
      <rect x={4} y={3.5} width={12} height={10.5} rx={2} fill="none" stroke="currentColor" strokeWidth={1.6} />
      <line x1={4} y1={8} x2={16} y2={8} stroke="currentColor" strokeWidth={1.6} />
      <line x1={7} y1={11.5} x2={7} y2={11.5} stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
      <line x1={13} y1={11.5} x2={13} y2={11.5} stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
      <line x1={6.5} y1={16.5} x2={5.5} y2={14.2} stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
      <line x1={13.5} y1={16.5} x2={14.5} y2={14.2} stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
    </>
  )
};

// The brigade's transport type, shown as a chip in the same style as the
// skill icons, so vehicle and skills read as one row of capability chips.
export function VehicleIcon({ vehicleType }: { vehicleType: VehicleType }) {
  return (
    <span className="skill-icon" role="img" aria-label={`Транспорт: ${vehicleLabel(vehicleType)}`} data-tooltip={vehicleLabel(vehicleType)}>
      <svg width={13} height={13} viewBox="0 0 20 20">
        {ICON_PATH[vehicleType]}
      </svg>
    </span>
  );
}
