-- name: delete_region_tickets(region_id)!
DELETE FROM tickets WHERE region_id = :region_id;

-- name: insert_tickets(region_id, external_id, type_bk, type_hd, required_skill, required_vehicle, priority, district, address, lon, lat, window_start, window_end, duration_min, status, received_at)*!
-- Window bounds and received_at are naive local time of the region, stored as given.
-- external_id is not unique: ticket numbers repeat in the source sets and no rule for
-- them is defined, so each row becomes its own ticket.
INSERT INTO tickets (region_id, external_id, type_bk, type_hd, required_skill,
                     required_vehicle, priority, district, address, geom,
                     window_start, window_end, duration_min, status, received_at)
VALUES (:region_id, :external_id, :type_bk, :type_hd, :required_skill,
        :required_vehicle, :priority, :district, :address,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
        :window_start, :window_end, :duration_min, :status, :received_at);

-- name: list_tickets_by_region(region_id)
-- Tickets of one region in any status, in id order. Datetimes are naive local time of
-- the region, returned as stored.
SELECT id, external_id, type_bk, type_hd, required_skill, required_vehicle,
       priority, district, address,
       ST_Y(geom) AS lat, ST_X(geom) AS lon,
       window_start, window_end, duration_min, status, received_at
FROM tickets
WHERE region_id = :region_id
ORDER BY id;

-- name: list_open_tickets_by_region(region_id)
-- Open tickets of one region (excludes completed and cancelled), in id order — the input
-- of plan building. Columns as list_tickets_by_region.
SELECT id, external_id, type_bk, type_hd, required_skill, required_vehicle,
       priority, district, address,
       ST_Y(geom) AS lat, ST_X(geom) AS lon,
       window_start, window_end, duration_min, status, received_at
FROM tickets
WHERE region_id = :region_id AND status NOT IN ('completed', 'cancelled')
ORDER BY id;

-- name: lock_ticket(ticket_id)^
-- One ticket by id, row locked until the transaction ends: a concurrent status change of
-- the same ticket waits and then reads the status this one wrote. None if there is no
-- such ticket. Columns as in list_tickets_by_region.
SELECT id, external_id, type_bk, type_hd, required_skill, required_vehicle,
       priority, district, address,
       ST_Y(geom) AS lat, ST_X(geom) AS lon,
       window_start, window_end, duration_min, status, received_at
FROM tickets
WHERE id = :ticket_id
FOR UPDATE;

-- name: update_ticket_status(ticket_id, status, cancelled_after_dispatch)^
-- Sets the status the service has already checked as a legal transition, and whether the
-- ticket was cancelled after its brigade had set out. Returns the ticket as lock_ticket does.
UPDATE tickets
SET status = :status,
    cancelled_after_dispatch = :cancelled_after_dispatch
WHERE id = :ticket_id
RETURNING id, external_id, type_bk, type_hd, required_skill, required_vehicle,
          priority, district, address,
          ST_Y(geom) AS lat, ST_X(geom) AS lon,
          window_start, window_end, duration_min, status, received_at;
