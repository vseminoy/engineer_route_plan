// Raw wire shape for POST /plan/{id}/replan, hand-written ahead of its
// generated client — the operation isn't in specs/openapi.yaml yet. Regions,
// engineers, tickets, data loading, and the plan build/get pair all use the
// generated types from src/api/generated/schemas instead. Nothing outside
// src/api reads these directly.
//
// This is also the last place a plan is still returned as a single
// synchronous shape (replan has no queued/running state of its own): mapped
// by mapLegacyReplanPlan in mappers.ts into a Plan with status: 'done'.

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

// GET /plan/{id}/compare is described only in prose so far, not yet part of
// the machine contract, and its documented example response has two metrics
// colliding on the same `main`/`baseline` keys in one JSON object — an
// unreliable shape to parse even once it lands. Both plans we compare
// (main + baseline) are already fetched in full for the Metrics tab, so the
// app derives the comparison client-side from PlanMetrics instead (see
// src/queries/usePlanCompare.ts) rather than depend on that endpoint.
