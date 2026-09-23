import { http } from './client';
import { mapEngineerRoster, mapPlan, mapRegion, mapTicketSummary } from './mappers';
import type { ApiEngineerListItem, ApiPlan, ApiRegion, ApiTicketListItem } from './types';
import type {
  Algorithm,
  EngineerRoster,
  Plan,
  RegionCode,
  ReplanEvent,
  Region,
  TicketStatus,
  TicketSummary
} from '@/types/domain';

export function getRegions(): Promise<Region[]> {
  return http.get<ApiRegion[]>('/regions').then((rows) => rows.map(mapRegion));
}

export function getEngineers(region: RegionCode): Promise<EngineerRoster[]> {
  return http
    .get<ApiEngineerListItem[]>(`/engineers?region=${encodeURIComponent(region)}`)
    .then((rows) => rows.map(mapEngineerRoster));
}

export function getTickets(region: RegionCode, planId?: number): Promise<TicketSummary[]> {
  const suffix = planId !== undefined ? `&plan_id=${planId}` : '';
  return http
    .get<ApiTicketListItem[]>(`/tickets?region=${encodeURIComponent(region)}${suffix}`)
    .then((rows) => rows.map(mapTicketSummary));
}

export function loadDemoDataset(region: RegionCode): Promise<{ region: RegionCode }> {
  // Seeds the backend's store for the region; the plan itself is built by buildPlan().
  return http.get(`/data/demo?region=${encodeURIComponent(region)}`);
}

export function uploadDataset(
  region: RegionCode,
  ticketsFile: File,
  engineersFile?: File
): Promise<{ region: RegionCode }> {
  const form = new FormData();
  form.append('region', region);
  form.append('tickets_file', ticketsFile);
  if (engineersFile) form.append('engineers_file', engineersFile);
  return http.post('/data/upload', form);
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
