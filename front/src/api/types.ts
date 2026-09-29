// Raw wire shapes exactly as docs/bft/05_spec_backend.md §4 returns them
// (snake_case JSON). Nothing outside src/api reads these directly.

export interface ApiRegion {
  code: string;
  name: string;
}

export interface ApiRouteStop {
  ticket_id: number;
  sequence_no: number;
  planned_arrival: string;
  travel_time_min: number;
  travel_distance_km: number;
  explanation: string;
}

export interface ApiEngineerRoute {
  engineer_id: number;
  name: string;
  route: ApiRouteStop[];
  total_distance_km: number;
  total_travel_time_min: number;
  idle_time_min: number;
}

export interface ApiUnassignedTicket {
  ticket_id: number;
  reason_code: string;
  explanation: string;
}

export interface ApiPlanMetrics {
  engineers_used: number;
  total_distance_km: number;
  distance_by_engineer: Record<string, number>;
  assigned_count: number;
  unassigned_count: number;
  idle_time_by_engineer_min: Record<string, number>;
  load_balance_std_dev?: number;
  plan_stability?: number;
}

export interface ApiPlanDiff {
  changed_assignments: Array<{
    ticket_id: number;
    before_engineer_id?: number;
    after_engineer_id?: number;
    before_sequence_no?: number;
    after_sequence_no?: number;
  }>;
  newly_assigned: number[];
  newly_unassigned: number[];
  reassigned_from_unavailable_engineer: number[];
  plan_stability: number;
}

export interface ApiPlan {
  plan_id: number;
  algorithm: string;
  parent_plan_id?: number;
  engineers: ApiEngineerRoute[];
  unassigned: ApiUnassignedTicket[];
  metrics: ApiPlanMetrics;
  diff?: ApiPlanDiff;
}

// GET /engineers and GET /tickets are specified in 05_spec_backend.md §4.1
// only as a one-line purpose ("список бригад региона с навыками и
// транспортом" / "список заявок региона") — no sample JSON body is given.
// These shapes are inferred from the `engineer` / `ticket` DDL in §3 and
// should be reconciled against the real endpoint once the backend ships it.
export interface ApiEngineerListItem {
  id: number;
  name: string;
  vehicle_type: string;
  skills: string[];
  shift_start: string; // 'HH:MM:SS'
  shift_end: string;
  start_lat: number;
  start_lon: number;
}

export interface ApiTicketListItem {
  id: number;
  required_skill: string;
  priority: string;
  address: string;
  window_start: string;
  window_end: string;
  duration_min: number;
  status: string;
  lat: number | null;
  lon: number | null;
}

// GET /plan/{id}/compare exists in the contract, but its documented example
// response has two metrics colliding on the same `main`/`baseline` keys in
// one JSON object — an unreliable shape to parse. Both plans we compare
// (main + baseline) are already fetched in full for the Metrics tab, so the
// app derives the comparison client-side from PlanMetrics instead (see
// src/queries/usePlanCompare.ts) rather than depend on that endpoint.
