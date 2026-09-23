// Domain types the app is written against — camelCase, exactly as specified
// in docs/bft/06_spec_frontend.md §5. Raw API responses (snake_case, per
// docs/bft/05_spec_backend.md §4) are mapped into these in src/api/mappers.ts;
// components never see the wire shape directly.

export type Skill = 'local_work' | 'connection' | 'emergency';
export type VehicleType = 'car' | 'foot' | 'bike' | 'public_transport';
export type Priority = 'normal' | 'urgent';
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
  | 'no_equipment'
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
  plannedArrival: string; // 'YYYY-MM-DD HH:MM', naive local time (no UTC conversion — BR-21)
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
  idleTimeMin: number; // FR-23 — display only, never compared to baseline
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
  idleTimeByEngineerMin: Record<string, number>; // FR-23, always present
  loadBalanceStdDev?: number;
  planStability?: number;
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

export interface Plan {
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

// One of the three replan events from 06_spec_frontend.md §3.7 / 05_spec_backend.md §4.3.
export type ReplanEvent =
  | {
      eventType: 'new_urgent_ticket';
      triggeredAt: string;
      ticket: {
        address: string;
        district?: string;
        lat?: number;
        lon?: number;
        windowStart: string;
        windowEnd: string;
        requiredSkill: 'emergency';
        durationMin: 80;
      };
    }
  | { eventType: 'ticket_cancelled'; triggeredAt: string; ticketId: number }
  | { eventType: 'engineer_unavailable'; triggeredAt: string; engineerId: number };

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

export interface ApiErrorShape {
  errorCode: string;
  message: string;
}
