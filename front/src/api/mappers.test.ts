import { describe, expect, it } from 'vitest';
import { mapDataLoadResult, mapEngineerRoster, mapTicketSummary } from './mappers';
import type { DataLoadResult, Engineer, Ticket } from './generated/schemas';

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
