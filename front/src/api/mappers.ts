import type {
  ApiEngineerListItem,
  ApiEngineerRoute,
  ApiPlan,
  ApiPlanDiff,
  ApiPlanMetrics,
  ApiRegion,
  ApiRouteStop,
  ApiTicketListItem,
  ApiUnassignedTicket
} from './types';
import { minutesSinceMidnight } from '@/lib/format';
import type {
  Algorithm,
  EngineerRoster,
  EngineerRoute,
  Plan,
  PlanDiff,
  PlanMetrics,
  Priority,
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

function mapUnassignedTicket(u: ApiUnassignedTicket): UnassignedTicket {
  return {
    ticketId: u.ticket_id,
    reasonCode: u.reason_code as UnassignedReason,
    explanation: u.explanation
  };
}

function mapMetrics(m: ApiPlanMetrics): PlanMetrics {
  return {
    engineersUsed: m.engineers_used,
    totalDistanceKm: m.total_distance_km,
    distanceByEngineer: m.distance_by_engineer,
    assignedCount: m.assigned_count,
    unassignedCount: m.unassigned_count,
    idleTimeByEngineerMin: m.idle_time_by_engineer_min,
    loadBalanceStdDev: m.load_balance_std_dev,
    planStability: m.plan_stability
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

export function mapPlan(api: ApiPlan): Plan {
  return {
    planId: api.plan_id,
    algorithm: api.algorithm as Algorithm,
    parentPlanId: api.parent_plan_id,
    engineers: api.engineers.map(mapEngineerRoute),
    unassigned: api.unassigned.map(mapUnassignedTicket),
    metrics: mapMetrics(api.metrics),
    diff: api.diff ? mapDiff(api.diff) : undefined
  };
}

export function mapRegion(api: ApiRegion): Region {
  return { code: api.code as RegionCode, name: api.name };
}

export function mapEngineerRoster(api: ApiEngineerListItem): EngineerRoster {
  return {
    engineerId: api.id,
    name: api.name,
    vehicleType: api.vehicle_type as VehicleType,
    skills: api.skills as Skill[],
    shiftStartMin: minutesSinceMidnight(api.shift_start),
    shiftEndMin: minutesSinceMidnight(api.shift_end),
    startLat: api.start_lat,
    startLon: api.start_lon
  };
}

export function mapTicketSummary(api: ApiTicketListItem): TicketSummary {
  return {
    ticketId: api.id,
    requiredSkill: api.required_skill as Skill,
    priority: api.priority as Priority,
    address: api.address,
    windowStartMin: minutesSinceMidnight(api.window_start),
    windowEndMin: minutesSinceMidnight(api.window_end),
    durationMin: api.duration_min,
    status: api.status as TicketStatus,
    lat: api.lat,
    lon: api.lon
  };
}
