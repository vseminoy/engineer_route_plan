import { describe, expect, it } from 'vitest';
import { mapDataLoadResult, mapEngineerRoster, mapPlan, mapPlanCompare, mapPlanReplanResult, mapTicketSummary } from './mappers';
import type { DataLoadResult, Engineer, Plan, PlanComparisonEntry, PlanReplanResult, Ticket } from './generated/schemas';

describe('mapEngineerRoster', () => {
  it('flattens the start point and converts shift bounds to minutes since midnight', () => {
    const api: Engineer = {
      id: 3,
      name: 'Бригада 3',
      vehicle_type: 'car',
      skills: ['connection', 'emergency'],
      shift_start: '08:00',
      shift_end: '20:00',
      start: { lat: 55.75, lon: 37.61 }
    };

    const roster = mapEngineerRoster(api);

    expect(roster).toEqual({
      engineerId: 3,
      name: 'Бригада 3',
      vehicleType: 'car',
      skills: ['connection', 'emergency'],
      shiftStartMin: 480,
      shiftEndMin: 1200,
      startLat: 55.75,
      startLon: 37.61
    });
  });
});

describe('mapTicketSummary', () => {
  it('carries the numeric priority rank and derives the window in minutes from the naive datetime', () => {
    const api: Ticket = {
      id: 42,
      external_id: 'T-1',
      type_bk: null,
      type_hd: 'Авария',
      required_skill: 'emergency',
      required_vehicle: null,
      priority: 1,
      district: null,
      address: 'ул. Ленина, 1',
      location: { lat: 55.0, lon: 37.0 },
      window_start: '2026-08-17T09:00:00',
      window_end: '2026-08-17T11:30:00',
      duration_min: 80,
      status: 'not_sent',
      received_at: '2026-08-17T08:00:00'
    };

    const summary = mapTicketSummary(api);

    expect(summary).toEqual({
      ticketId: 42,
      requiredSkill: 'emergency',
      priority: 1,
      address: 'ул. Ленина, 1',
      windowStartMin: 540,
      windowEndMin: 690,
      durationMin: 80,
      status: 'not_sent',
      lat: 55.0,
      lon: 37.0
    });
  });
});

describe('mapPlan', () => {
  it('maps a running build to a status with no engineers/unassigned/metrics yet', () => {
    const api: Plan = { plan_id: 42, algorithm: 'or_tools', status: 'running', engineer_set_id: 1 };

    expect(mapPlan(api)).toEqual({ planId: 42, algorithm: 'or_tools', status: 'running' });
  });

  it('maps a failed build to its reason, with no engineers/unassigned/metrics', () => {
    const api: Plan = {
      plan_id: 42,
      algorithm: 'or_tools',
      status: 'failed',
      engineer_set_id: 1,
      failed_reason: 'osrm_unavailable'
    };

    expect(mapPlan(api)).toEqual({
      planId: 42,
      algorithm: 'or_tools',
      status: 'failed',
      failedReason: 'osrm_unavailable'
    });
  });

  it('maps a failed build stopped by the server-shutdown sweep', () => {
    const api: Plan = { plan_id: 42, algorithm: 'or_tools', status: 'failed', engineer_set_id: 1, failed_reason: 'shutdown' };

    expect(mapPlan(api).failedReason).toBe('shutdown');
  });

  it('maps engineers/unassigned/metrics straight from the API response when done, keeping the naive arrival time as-is', () => {
    const api: Plan = {
      plan_id: 42,
      algorithm: 'or_tools',
      status: 'done',
      engineer_set_id: 1,
      engineers: [
        {
          engineer_id: 3,
          name: 'Бригада Соколов',
          route: [
            {
              ticket_id: 101,
              sequence_no: 1,
              planned_arrival: '2026-08-17T10:05:00',
              travel_time_min: 18,
              travel_distance_km: 6.2,
              explanation: 'Назначена бригада «Соколов».'
            }
          ],
          total_distance_km: 21.4,
          total_travel_time_min: 54,
          idle_time_min: 126
        },
        { engineer_id: 5, name: 'Бригада Петров', route: [], total_distance_km: 0, total_travel_time_min: 0, idle_time_min: 480 }
      ],
      unassigned: [{ ticket_id: 118, reason_code: 'no_time_slot', explanation: 'Не успевает ни одна бригада.' }],
      metrics: {
        engineers_used: 1,
        total_distance_km: 21.4,
        distance_by_engineer: { '3': 21.4, '5': 0 },
        assigned_count: 1,
        unassigned_count: 1,
        idle_time_by_engineer_min: { '3': 126, '5': 480 }
      }
    };

    const plan = mapPlan(api);

    expect(plan.status).toBe('done');
    expect(plan.engineers?.[0].route[0].plannedArrival).toBe('2026-08-17T10:05:00');
    expect(plan.metrics).toEqual({
      engineersUsed: 1,
      totalDistanceKm: 21.4,
      distanceByEngineer: { '3': 21.4, '5': 0 },
      assignedCount: 1,
      unassignedCount: 1,
      idleTimeByEngineerMin: { '3': 126, '5': 480 }
    });
  });
});

describe('mapPlanCompare', () => {
  it('reshapes the compare_plan entries into the fixed engineersUsed/totalDistanceKm pair', () => {
    const entries: PlanComparisonEntry[] = [
      { metric: 'engineers_used', main: 9, baseline: 13, delta: -4 },
      { metric: 'total_distance_km', main: 187.3, baseline: 244.9, delta: -57.6 }
    ];

    expect(mapPlanCompare(entries)).toEqual({
      engineersUsed: { main: 9, baseline: 13, delta: -4 },
      totalDistanceKm: { main: 187.3, baseline: 244.9, delta: -57.6 }
    });
  });

  it('throws if the response is missing a mandatory metric', () => {
    expect(() => mapPlanCompare([{ metric: 'engineers_used', main: 9, baseline: 13, delta: -4 }])).toThrow();
  });
});

describe('mapPlanReplanResult', () => {
  it('maps the synchronous replan response to a done plan with its diff', () => {
    const api: PlanReplanResult = {
      plan_id: 43,
      parent_plan_id: 42,
      algorithm: 'or_tools',
      engineer_set_id: 1,
      status: 'done',
      engineers: [
        {
          engineer_id: 3,
          name: 'Бригада Соколов',
          route: [
            {
              ticket_id: 101,
              sequence_no: 1,
              planned_arrival: '2026-08-17T10:05:00',
              travel_time_min: 18,
              travel_distance_km: 6.2,
              explanation: 'Назначена бригада «Соколов».'
            }
          ],
          total_distance_km: 21.4,
          total_travel_time_min: 54,
          idle_time_min: 126
        }
      ],
      unassigned: [],
      metrics: {
        engineers_used: 1,
        total_distance_km: 21.4,
        distance_by_engineer: { '3': 21.4 },
        assigned_count: 1,
        unassigned_count: 0,
        idle_time_by_engineer_min: { '3': 126 }
      },
      diff: {
        changed_assignments: [],
        newly_assigned: [101],
        newly_unassigned: [],
        reassigned_from_unavailable_engineer: [],
        plan_stability: 1
      }
    };

    const plan = mapPlanReplanResult(api);

    expect(plan.status).toBe('done');
    expect(plan.planId).toBe(43);
    expect(plan.parentPlanId).toBe(42);
    expect(plan.engineers?.[0].route[0].plannedArrival).toBe('2026-08-17T10:05:00');
    expect(plan.diff).toEqual({
      changedAssignments: [],
      newlyAssigned: [101],
      newlyUnassigned: [],
      reassignedFromUnavailableEngineer: [],
      planStability: 1
    });
  });
});

describe('mapDataLoadResult', () => {
  it('translates snake_case counts and invalid rows into the domain shape', () => {
    const api: DataLoadResult = {
      region: 'east',
      engineers: 12,
      tickets: 98,
      rows_total: 100,
      rows_skipped: 1,
      rows_invalid: [{ row: 5, column: 'Начало', reason: 'bad_datetime' }]
    };

    expect(mapDataLoadResult(api)).toEqual({
      region: 'east',
      engineersCount: 12,
      ticketsCount: 98,
      rowsTotal: 100,
      rowsSkipped: 1,
      invalidRows: [{ row: 5, column: 'Начало', reason: 'bad_datetime' }]
    });
  });
});
