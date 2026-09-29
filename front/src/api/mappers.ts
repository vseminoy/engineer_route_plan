import type { ApiPlan, ApiPlanDiff } from './types';
import type {
  DataLoadResult as ApiDataLoadResult,
  Engineer,
  EngineerRoute as ApiEngineerRoute,
  Plan as GeneratedPlan,
  Region as ApiRegion,
  Ticket,
  Visit as ApiRouteStop
} from './generated/schemas';
import { minutesSinceMidnight } from '@/lib/format';
import type {
  Algorithm,
  DataLoadResult,
  EngineerRoster,
  EngineerRoute,
  Plan,
  PlanDiff,
  PlanFailedReason,
  PlanMetrics,
  PlanStatus,
  Region,
  RegionCode,
  RouteStop,
  Skill,
  TicketStatus,
  TicketSummary,
  UnassignedReason,
  UnassignedTicket,
  VehicleType
} from '@/types/domain';

// Shared by the generated build/get response and the legacy hand-written
// replan one (F6) — both name their route stop, engineer route and
// unassigned-ticket objects identically, so one set of mappers covers both.
function mapRouteStop(s: ApiRouteStop): RouteStop {
  return {
    ticketId: s.ticket_id,
    sequenceNo: s.sequence_no,
    plannedArrival: s.planned_arrival,
    travelTimeMin: s.travel_time_min,
    travelDistanceKm: s.travel_distance_km,
    explanation: s.explanation
  };
}

function mapEngineerRoute(e: ApiEngineerRoute): EngineerRoute {
  return {
    engineerId: e.engineer_id,
    name: e.name,
    route: e.route.map(mapRouteStop),
    totalDistanceKm: e.total_distance_km,
    totalTravelTimeMin: e.total_travel_time_min,
    idleTimeMin: e.idle_time_min
  };
}

// `reason_code` is typed as plain `string` here (rather than the generated
// 5-value union) so this one function also accepts the legacy replan wire
// shape, whose hand-written type doesn't narrow it either.
function mapUnassignedTicket(u: { ticket_id: number; reason_code: string; explanation: string }): UnassignedTicket {
  return {
    ticketId: u.ticket_id,
    reasonCode: u.reason_code as UnassignedReason,
    explanation: u.explanation
  };
}

// The done response carries engineers/unassigned but no metrics object yet
// (the backend doesn't send one). The two mandatory comparison metrics, and
// the always-present per-engineer breakdowns, are all fully derivable from
// engineers/unassigned themselves, so they're computed here instead of
// waiting on that field. load_balance_std_dev/plan_stability stay unset
// until the backend actually sends them.
function computePlanMetrics(engineers: EngineerRoute[], unassigned: UnassignedTicket[]): PlanMetrics {
  const distanceByEngineer: Record<string, number> = {};
  const idleTimeByEngineerMin: Record<string, number> = {};
  let engineersUsed = 0;
  let totalDistanceKm = 0;
  let assignedCount = 0;

  for (const e of engineers) {
    distanceByEngineer[e.engineerId] = e.totalDistanceKm;
    idleTimeByEngineerMin[e.engineerId] = e.idleTimeMin;
    totalDistanceKm += e.totalDistanceKm;
    assignedCount += e.route.length;
    if (e.route.length > 0) engineersUsed += 1;
  }

  return {
    engineersUsed,
    totalDistanceKm,
    distanceByEngineer,
    assignedCount,
    unassignedCount: unassigned.length,
    idleTimeByEngineerMin
  };
}

function mapDiff(d: ApiPlanDiff): PlanDiff {
  return {
    changedAssignments: d.changed_assignments.map((c) => ({
      ticketId: c.ticket_id,
      beforeEngineerId: c.before_engineer_id,
      afterEngineerId: c.after_engineer_id,
      beforeSequenceNo: c.before_sequence_no,
      afterSequenceNo: c.after_sequence_no
    })),
    newlyAssigned: d.newly_assigned,
    newlyUnassigned: d.newly_unassigned,
    reassignedFromUnavailableEngineer: d.reassigned_from_unavailable_engineer,
    planStability: d.plan_stability
  };
}

// POST /plan/build (202) and GET /plan/{id} share this response shape —
// running has neither engineers/unassigned nor a reason, done has the
// former, failed has the latter.
export function mapPlan(api: GeneratedPlan): Plan {
  const base = { planId: api.plan_id, algorithm: api.algorithm as Algorithm, status: api.status as PlanStatus };

  if (api.status === 'done') {
    const engineers = (api.engineers ?? []).map(mapEngineerRoute);
    const unassigned = (api.unassigned ?? []).map(mapUnassignedTicket);
    return { ...base, engineers, unassigned, metrics: computePlanMetrics(engineers, unassigned) };
  }
  if (api.status === 'failed') {
    return { ...base, failedReason: api.failed_reason as PlanFailedReason };
  }
  return base;
}

// POST /plan/{id}/replan (F6) isn't in specs/openapi.yaml yet and answers
// synchronously with the pre-async plan shape (metrics/diff included on the
// wire, no running state of its own) — mapped separately until that endpoint
// gets a real spec and a generated client.
export function mapLegacyReplanPlan(api: ApiPlan): Plan {
  const engineers = api.engineers.map(mapEngineerRoute);
  const unassigned = api.unassigned.map(mapUnassignedTicket);
  return {
    planId: api.plan_id,
    algorithm: api.algorithm as Algorithm,
    status: 'done',
    parentPlanId: api.parent_plan_id,
    engineers,
    unassigned,
    metrics: computePlanMetrics(engineers, unassigned),
    diff: api.diff ? mapDiff(api.diff) : undefined
  };
}

export function mapRegion(api: ApiRegion): Region {
  return { code: api.code as RegionCode, name: api.name };
}

export function mapEngineerRoster(api: Engineer): EngineerRoster {
  return {
    engineerId: api.id,
    name: api.name,
    vehicleType: api.vehicle_type as VehicleType,
    skills: api.skills as Skill[],
    shiftStartMin: minutesSinceMidnight(api.shift_start),
    shiftEndMin: minutesSinceMidnight(api.shift_end),
    startLat: api.start.lat,
    startLon: api.start.lon
  };
}

export function mapTicketSummary(api: Ticket): TicketSummary {
  return {
    ticketId: api.id,
    requiredSkill: api.required_skill as Skill,
    priority: api.priority,
    address: api.address,
    windowStartMin: minutesSinceMidnight(api.window_start),
    windowEndMin: minutesSinceMidnight(api.window_end),
    durationMin: api.duration_min,
    status: api.status as TicketStatus,
    lat: api.location.lat,
    lon: api.location.lon
  };
}

export function mapDataLoadResult(api: ApiDataLoadResult): DataLoadResult {
  return {
    region: api.region as RegionCode,
    engineersCount: api.engineers,
    ticketsCount: api.tickets,
    rowsTotal: api.rows_total,
    rowsSkipped: api.rows_skipped,
    invalidRows: api.rows_invalid.map((r) => ({ row: r.row, column: r.column, reason: r.reason }))
  };
}
