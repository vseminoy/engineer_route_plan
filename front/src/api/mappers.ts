import type { ApiPlan, ApiPlanDiff } from './types';
import type {
  DataLoadResult as ApiDataLoadResult,
  Engineer,
  EngineerRoute as ApiEngineerRoute,
  Plan as GeneratedPlan,
  PlanComparisonEntry,
  PlanMetrics as ApiPlanMetrics,
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
  PlanCompare,
  PlanDiff,
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

function mapPlanMetrics(m: ApiPlanMetrics): PlanMetrics {
  return {
    engineersUsed: m.engineers_used,
    totalDistanceKm: m.total_distance_km,
    distanceByEngineer: m.distance_by_engineer,
    assignedCount: m.assigned_count,
    unassignedCount: m.unassigned_count,
    idleTimeByEngineerMin: m.idle_time_by_engineer_min
  };
}

// Fallback for the legacy replan response (mapLegacyReplanPlan below), which
// has no metrics field of its own on the wire — derived from
// engineers/unassigned until F6 gives replan a real spec and client.
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
// running has neither engineers/unassigned/metrics nor a reason, done has
// the former (engineers/unassigned/metrics all null until then), failed has
// the latter.
export function mapPlan(api: GeneratedPlan): Plan {
  const base = { planId: api.plan_id, algorithm: api.algorithm as Algorithm, status: api.status as PlanStatus };

  if (api.status === 'done') {
    const engineers = (api.engineers ?? []).map(mapEngineerRoute);
    const unassigned = (api.unassigned ?? []).map(mapUnassignedTicket);
    const metrics = api.metrics ? mapPlanMetrics(api.metrics) : computePlanMetrics(engineers, unassigned);
    return { ...base, engineers, unassigned, metrics };
  }
  if (api.status === 'failed') {
    return { ...base, failedReason: api.failed_reason ?? undefined };
  }
  return base;
}

// GET /plan/{id}/compare returns one entry per mandatory metric
// (engineers_used, total_distance_km); reshaped into the fixed pair the
// Metrics tab renders instead of an array the caller has to search.
export function mapPlanCompare(entries: PlanComparisonEntry[]): PlanCompare {
  const byMetric = new Map(entries.map((e) => [e.metric, e]));
  const engineersUsed = byMetric.get('engineers_used');
  const totalDistanceKm = byMetric.get('total_distance_km');
  if (!engineersUsed || !totalDistanceKm) {
    throw new Error('compare_plan response is missing a mandatory metric');
  }
  return {
    engineersUsed: { main: engineersUsed.main, baseline: engineersUsed.baseline, delta: engineersUsed.delta },
    totalDistanceKm: { main: totalDistanceKm.main, baseline: totalDistanceKm.baseline, delta: totalDistanceKm.delta }
  };
}

// POST /plan/{id}/replan has a real spec and a generated client now, but F6
// (which wires ReplanTab to it) hasn't started — this still maps the
// hand-written pre-async shape (metrics/diff on the wire, no running state)
// that `replan` in endpoints.ts calls via `http.post` directly. F6 replaces
// both with the generated `replanPlan` client and this mapper.
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
