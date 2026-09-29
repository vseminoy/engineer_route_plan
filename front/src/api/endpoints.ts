import { http, unwrap } from './client';
import { listEngineers, listRegions, listTickets, loadDemoData, uploadRegionData } from './generated/engineerRoutePlanAPI';
import { mapDataLoadResult, mapEngineerRoster, mapPlan, mapRegion, mapTicketSummary } from './mappers';
import type { DataLoadResult as ApiDataLoadResult, Engineer, Region as ApiRegion, Ticket } from './generated/schemas';
import type { ApiPlan } from './types';
import type {
  Algorithm,
  DataLoadResult,
  EngineerRoster,
  Plan,
  RegionCode,
  ReplanEvent,
  Region,
  TicketStatus,
  TicketSummary
} from '@/types/domain';

export function getRegions(): Promise<Region[]> {
  return unwrap<ApiRegion[]>(listRegions(), 200).then((rows) => rows.map(mapRegion));
}

export function getEngineers(region: RegionCode): Promise<EngineerRoster[]> {
  return unwrap<Engineer[]>(listEngineers({ region }), 200).then((rows) => rows.map(mapEngineerRoster));
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

export function buildPlan(region: RegionCode, planDate: string, algorithm: Algorithm): Promise<Plan> {
  return http
    .post<ApiPlan>('/plan/build', { region, plan_date: planDate, algorithm })
    .then(mapPlan);
}

export function getPlan(planId: number): Promise<Plan> {
  return http.get<ApiPlan>(`/plan/${planId}`).then(mapPlan);
}

function replanEventToPayload(event: ReplanEvent): Record<string, unknown> {
  switch (event.eventType) {
    case 'new_urgent_ticket':
      return {
        event_type: 'new_urgent_ticket',
        triggered_at: event.triggeredAt,
        ticket: {
          address: event.ticket.address,
          district: event.ticket.district,
          lat: event.ticket.lat,
          lon: event.ticket.lon,
          window_start: event.ticket.windowStart,
          window_end: event.ticket.windowEnd,
          required_skill: event.ticket.requiredSkill,
          duration_min: event.ticket.durationMin
        }
      };
    case 'ticket_cancelled':
      return { event_type: 'ticket_cancelled', triggered_at: event.triggeredAt, ticket_id: event.ticketId };
    case 'engineer_unavailable':
      return {
        event_type: 'engineer_unavailable',
        triggered_at: event.triggeredAt,
        engineer_id: event.engineerId
      };
  }
}

export function replan(planId: number, event: ReplanEvent): Promise<Plan> {
  return http.post<ApiPlan>(`/plan/${planId}/replan`, replanEventToPayload(event)).then(mapPlan);
}

export function setTicketStatus(ticketId: number, status: TicketStatus): Promise<void> {
  return http.patch(`/tickets/${ticketId}/status`, { status });
}
