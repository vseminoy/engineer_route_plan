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
