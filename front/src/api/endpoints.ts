import { unwrap } from './client';
import {
  buildPlan as postPlanBuild,
  changeTicketStatus,
  comparePlan as getPlanCompareRequest,
  createEngineerSet as postEngineerSet,
  deleteEngineerSet as deleteEngineerSetRequest,
  deletePlan as deletePlanRequest,
  getPlan as getPlanRequest,
  listEngineerSets,
  listEngineers,
  listPlans,
  listRegions,
  listTickets,
  loadDemoData,
  replanPlan,
  uploadRegionData
} from './generated/engineerRoutePlanAPI';
import {
  mapDataLoadResult,
  mapEngineerRoster,
  mapEngineerSet,
  mapPlan,
  mapPlanCompare,
  mapPlanReplanResult,
  mapPlanSummary,
  mapRegion,
  mapTicketSummary
} from './mappers';
import type {
  DataLoadResult as ApiDataLoadResult,
  Engineer,
  EngineerSet as ApiEngineerSet,
  EngineerSetCreateRequest,
  Plan as ApiPlanGenerated,
  PlanComparisonEntry,
  PlanReplanResult,
  PlanSummary as ApiPlanSummary,
  Region as ApiRegion,
  ReplanEventRequest,
  Ticket
} from './generated/schemas';
import type {
  Algorithm,
  DataLoadResult,
  EngineerRoster,
  EngineerSet,
  Plan,
  PlanCompare,
  PlanSummary,
  RegionCode,
  ReplanEvent,
  Region,
  TicketStatus,
  TicketSummary
} from '@/types/domain';

export function getRegions(): Promise<Region[]> {
  return unwrap<ApiRegion[]>(listRegions(), 200).then((rows) => rows.map(mapRegion));
}

export function getEngineers(region: RegionCode, engineerSetId?: number | null): Promise<EngineerRoster[]> {
  return unwrap<Engineer[]>(
    listEngineers(engineerSetId ? { region, engineer_set_id: engineerSetId } : { region }),
    200
  ).then((rows) => rows.map(mapEngineerRoster));
}

export function getEngineerSets(region: RegionCode): Promise<EngineerSet[]> {
  return unwrap<ApiEngineerSet[]>(listEngineerSets({ region }), 200).then((rows) => rows.map(mapEngineerSet));
}

export function createEngineerSet(request: EngineerSetCreateRequest): Promise<EngineerSet> {
  return unwrap<ApiEngineerSet>(postEngineerSet(request), 201).then(mapEngineerSet);
}

export function deleteEngineerSet(engineerSetId: number): Promise<void> {
  return unwrap<void>(deleteEngineerSetRequest(engineerSetId), 204);
}

export function getTickets(region: RegionCode): Promise<TicketSummary[]> {
  return unwrap<Ticket[]>(listTickets({ region }), 200).then((rows) => rows.map(mapTicketSummary));
}

export function loadDemoDataset(region: RegionCode): Promise<DataLoadResult> {
  return unwrap<ApiDataLoadResult>(loadDemoData({ region }), 200).then(mapDataLoadResult);
}

export function uploadDataset(region: RegionCode, ticketsFile: File): Promise<DataLoadResult> {
  return unwrap<ApiDataLoadResult>(uploadRegionData({ region, tickets_file: ticketsFile }), 200).then(
    mapDataLoadResult
  );
}

// Queues the build and returns the 202 stub (status: 'running', plan_id) — the
// caller polls getPlan(planId) for the result. No engineerSetId (or null) —
// the backend builds for the region's default set.
export function buildPlan(
  region: RegionCode,
  planDate: string,
  algorithm: Algorithm,
  engineerSetId?: number | null
): Promise<Plan> {
  return unwrap<ApiPlanGenerated>(
    postPlanBuild({ region, plan_date: planDate, algorithm, engineer_set_id: engineerSetId ?? null }),
    202
  ).then(mapPlan);
}

export function getPlan(planId: number): Promise<Plan> {
  return unwrap<ApiPlanGenerated>(getPlanRequest(planId), 200).then(mapPlan);
}

// Every plan built for the region/engineer set, newest first — used to
// recover which baseline_fcfs plan pairs with a main plan when it wasn't
// just built in this session (see usePlanCompare).
export function getPlans(region: RegionCode, engineerSetId?: number | null): Promise<PlanSummary[]> {
  return unwrap<ApiPlanSummary[]>(
    listPlans(engineerSetId ? { region, engineer_set_id: engineerSetId } : { region }),
    200
  ).then((rows) => rows.map(mapPlanSummary));
}

export function deletePlan(planId: number): Promise<void> {
  return unwrap<void>(deletePlanRequest(planId), 204);
}

// Both plans must already be status: 'done' — the backend rejects the
// comparison with a 400 otherwise.
export function comparePlan(planId: number, baselinePlanId: number): Promise<PlanCompare> {
  return unwrap<PlanComparisonEntry[]>(getPlanCompareRequest(planId, { baseline_plan_id: baselinePlanId }), 200).then(
    mapPlanCompare
  );
}

// type_hd is informational only for this event (the server always assigns
// required_skill=emergency itself) — a fixed label for a ticket the
// dispatcher raises by hand, not read from an external system.
const MANUAL_INCIDENT_TYPE_HD = 'Авария (заведена диспетчером)';

export function replanEventToRequest(event: ReplanEvent): ReplanEventRequest {
  switch (event.eventType) {
    case 'new_urgent_ticket':
      return {
        event_type: 'new_urgent_ticket',
        triggered_at: event.triggeredAt,
        ticket: {
          // No external-system ticket number for a dispatcher-raised
          // incident — derived from triggered_at so it stays unique.
          external_id: `manual-${event.triggeredAt}`,
          type_bk: null,
          type_hd: MANUAL_INCIDENT_TYPE_HD,
          district: null,
          address: event.address,
          location: { lat: event.lat, lon: event.lon },
          required_vehicle: null
        },
        ...(event.reactionMin !== undefined ? { reaction_min: event.reactionMin } : {})
      };
    case 'ticket_cancelled':
      return { event_type: 'ticket_cancelled', triggered_at: event.triggeredAt, ticket_id: event.ticketId };
    case 'engineer_unavailable':
      return { event_type: 'engineer_unavailable', triggered_at: event.triggeredAt, engineer_id: event.engineerId };
  }
}

export function replan(planId: number, event: ReplanEvent): Promise<Plan> {
  return unwrap<PlanReplanResult>(replanPlan(planId, replanEventToRequest(event)), 200).then(mapPlanReplanResult);
}

export function setTicketStatus(ticketId: number, status: TicketStatus): Promise<TicketSummary> {
  return unwrap<Ticket>(changeTicketStatus(ticketId, { status }), 200).then(mapTicketSummary);
}
