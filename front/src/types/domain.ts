// Domain types the app is written against — camelCase, independent of the
// wire shape. Raw API responses (snake_case) are mapped into these in
// src/api/mappers.ts; components never see the wire shape directly.

export type Skill = 'local_work' | 'connection' | 'emergency';
export type VehicleType = 'car' | 'foot' | 'bike' | 'public_transport';

// Rank >= 1, smaller is more urgent: 1 — авария, 2 — подключение, 3 — ремонт/дозаказ.
export type Priority = number;
export const URGENT_PRIORITY: Priority = 1;

export type TicketStatus =
  | 'not_sent'
  | 'sent'
  | 'en_route'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'overdue';
export type UnassignedReason =
  | 'no_skill'
  | 'no_time_slot'
  | 'no_vehicle'
  | 'shift_overflow'
  | 'all_eligible_engineers_booked_elsewhere';

export type Algorithm = 'or_tools' | 'baseline_fcfs';

export type RegionCode = 'east' | 'south_east' | 'south_center';

export interface Region {
  code: RegionCode;
  name: string;
}

export interface RouteStop {
  ticketId: number;
  sequenceNo: number;
  plannedArrival: string; // naive local datetime, ISO-8601 without an offset ('2026-08-17T10:05:00')
  travelTimeMin: number;
  travelDistanceKm: number;
  explanation: string;
}

export interface EngineerRoute {
  engineerId: number;
  name: string;
  route: RouteStop[];
  totalDistanceKm: number;
  totalTravelTimeMin: number;
  idleTimeMin: number; // display only, never compared to baseline
}

export interface UnassignedTicket {
  ticketId: number;
  reasonCode: UnassignedReason;
  explanation: string;
}

export interface PlanMetrics {
  engineersUsed: number;
  totalDistanceKm: number;
  distanceByEngineer: Record<string, number>;
  assignedCount: number;
  unassignedCount: number;
  idleTimeByEngineerMin: Record<string, number>; // always present, display only
}

export interface PlanDiff {
  changedAssignments: Array<{
    ticketId: number;
    beforeEngineerId?: number;
    afterEngineerId?: number;
    beforeSequenceNo?: number;
    afterSequenceNo?: number;
  }>;
  newlyAssigned: number[];
  newlyUnassigned: number[];
  reassignedFromUnavailableEngineer: number[];
  planStability: number;
}

// POST /plan/build queues the build and answers 202 before it finishes;
// GET /plan/{id} returns the same shape in whichever of the three states the
// build is currently in — poll it until status stops being 'running'.
export type PlanStatus = 'running' | 'done' | 'failed';

// osrm_unavailable — маршрутный сервис недоступен; db_unavailable — недоступна
// БД при сохранении плана; build_error — непредвиденная ошибка построения;
// timeout — расчёт прервали, не уложившись в отведённое время; shutdown —
// план остался running на момент остановки сервера и был закрыт при следующем запуске.
export type PlanFailedReason = 'osrm_unavailable' | 'db_unavailable' | 'build_error' | 'timeout' | 'shutdown';

export interface Plan {
  planId: number;
  algorithm: Algorithm;
  status: PlanStatus;
  parentPlanId?: number;
  // Present only once status === 'done'.
  engineers?: EngineerRoute[];
  unassigned?: UnassignedTicket[];
  metrics?: PlanMetrics;
  // Present only once status === 'failed'.
  failedReason?: PlanFailedReason;
  diff?: PlanDiff;
}

// The view every plan-detail component actually renders against: a Plan
// whose build has finished, so the fields that only exist once status ===
// 'done' are no longer optional. PlanScreen builds one of these after
// checking `plan.status` and passes it down instead of the raw Plan.
export interface DonePlan {
  planId: number;
  algorithm: Algorithm;
  parentPlanId?: number;
  engineers: EngineerRoute[];
  unassigned: UnassignedTicket[];
  metrics: PlanMetrics;
  diff?: PlanDiff;
}

export interface PlanCompare {
  engineersUsed: { main: number; baseline: number; delta: number };
  totalDistanceKm: { main: number; baseline: number; delta: number };
}

// The two replan events the dispatcher can raise from the UI. The contract
// allows a third, new_ticket (a non-urgent ticket arriving mid-day), with no
// form for it here — nothing in the app needs it yet.
export type ReplanEvent =
  | {
      eventType: 'new_urgent_ticket';
      triggeredAt: string;
      address: string;
      lat: number;
      lon: number;
      reactionMin?: number;
    }
  | { eventType: 'ticket_cancelled'; triggeredAt: string; ticketId: number };

// From GET /engineers — roster data the /plan responses don't carry
// themselves (skills for the skill-icon chips, shift bounds for the
// per-brigade occupancy timeline).
export interface EngineerRoster {
  engineerId: number;
  name: string;
  vehicleType: VehicleType;
  skills: Skill[];
  shiftStartMin: number; // minutes since midnight
  shiftEndMin: number;
  startLat: number;
  startLon: number;
}

// From GET /tickets — the fields a RouteStop doesn't carry (window, duration)
// but the occupancy timeline and "окно HH:MM–HH:MM" line need.
export interface TicketSummary {
  ticketId: number;
  requiredSkill: Skill;
  priority: Priority;
  address: string;
  windowStartMin: number; // minutes since midnight, naive local time
  windowEndMin: number;
  durationMin: number;
  status: TicketStatus;
  lat: number | null;
  lon: number | null;
}

// Why a row of the uploaded file (or the demo dataset) did not become a ticket —
// POST /data/upload and POST /data/demo return one per rejected row.
export type InvalidRowReason =
  | 'missing_field'
  | 'field_too_long'
  | 'bad_datetime'
  | 'window_order'
  | 'unknown_type'
  | 'unknown_status'
  | 'address_not_found';

export interface InvalidRow {
  row: number;
  column: string | null;
  reason: InvalidRowReason;
}

// Result of POST /data/upload or POST /data/demo — replaces the region's tickets
// (and refreshes its brigades' start points) in one transaction.
export interface DataLoadResult {
  region: RegionCode;
  engineersCount: number;
  ticketsCount: number;
  rowsTotal: number;
  rowsSkipped: number;
  invalidRows: InvalidRow[];
}
