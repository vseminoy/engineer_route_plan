-- name: delete_region_engineers(region_id)!
DELETE FROM engineers WHERE region_id = :region_id;

-- name: insert_engineers(region_id, name, start_lon, start_lat, shift_start, shift_end, vehicle_type, skills)*!
-- Shift times are local time of the region; skills are 1 to 3 values.
INSERT INTO engineers (region_id, name, start_geom, shift_start, shift_end,
                       vehicle_type, skills)
VALUES (:region_id, :name, ST_SetSRID(ST_MakePoint(:start_lon, :start_lat), 4326),
        :shift_start, :shift_end, :vehicle_type, :skills);
