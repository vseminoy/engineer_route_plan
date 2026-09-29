import { afterEach, describe, expect, it, vi } from 'vitest';
import { setTicketStatus } from './endpoints';
import { ApiError } from './client';
import type { Ticket } from './generated/schemas';

function stubFetch(response: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

async function catchError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected the promise to reject');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const apiTicket: Ticket = {
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
  status: 'en_route',
  received_at: '2026-08-17T08:00:00'
};

describe('setTicketStatus', () => {
  it('maps the 200 response to the domain ticket summary', async () => {
    stubFetch(
      new Response(JSON.stringify(apiTicket), { status: 200, headers: { 'Content-Type': 'application/json' } })
    );

    const summary = await setTicketStatus(42, 'en_route');

    expect(summary).toEqual({
      ticketId: 42,
      requiredSkill: 'emergency',
      priority: 1,
      address: 'ул. Ленина, 1',
      windowStartMin: 540,
      windowEndMin: 690,
      durationMin: 80,
      status: 'en_route',
      lat: 55.0,
      lon: 37.0
    });
  });

  it('rejects an invalid transition with the 400 message as-is', async () => {
    stubFetch(
      new Response(JSON.stringify({ message: 'Недопустимый переход статуса' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const err = (await catchError(setTicketStatus(42, 'completed'))) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.body && !('fields' in err.body) ? err.body.message : undefined).toBe('Недопустимый переход статуса');
  });

  it('rejects a missing ticket with a bodyless 404', async () => {
    stubFetch(new Response(null, { status: 404 }));

    const err = (await catchError(setTicketStatus(999, 'sent'))) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.body).toBeUndefined();
  });
});
