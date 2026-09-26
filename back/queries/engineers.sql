-- name: delete_region_engineers(region_id)!
DELETE FROM engineers WHERE region_id = :region_id;

-- name: insert_engineers(region_id, name, start_lon, start_lat, shift_start, shift_end, vehicle_type, skills)*!
-- Shift times are local time of the region; skills are 1 to 3 values.
INSERT INTO engineers (region_id, name, start_geom, shift_start, shift_end,
                       vehicle_type, skills)
VALUES (:region_id, :name, ST_SetSRID(ST_MakePoint(:start_lon, :start_lat), 4326),
        :shift_start, :shift_end, :vehicle_type, :skills);

-- name: list_region_roster(region_id)
-- The region's brigades as the generator describes them: the loader keeps them when the
-- generator's roster is the same and replaces them otherwise.
SELECT name, skills, vehicle_type, shift_start, shift_end
FROM engineers
WHERE region_id = :region_id;

-- name: update_engineer_starts(region_id, name, start_lon, start_lat)*!
-- Moves a kept brigade's start point; its id and everything else stay as they are.
UPDATE engineers
SET start_geom = ST_SetSRID(ST_MakePoint(:start_lon, :start_lat), 4326)
WHERE region_id = :region_id AND name = :name;

-- name: list_engineers_by_region(region_id)
-- Brigades of one region, in id order.
SELECT id, name, vehicle_type, skills, shift_start, shift_end,
       ST_Y(start_geom) AS start_lat, ST_X(start_geom) AS start_lon
FROM engineers
WHERE region_id = :region_id
ORDER BY id;
