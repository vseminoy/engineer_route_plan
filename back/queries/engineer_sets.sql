-- name: list_engineer_sets_by_region(region_id)
-- Every set of the region, by id — default first, since it is always inserted first.
SELECT id, name, kind, engineers, morning_share, evening_share, seed
FROM engineer_sets
WHERE region_id = :region_id
ORDER BY id;

-- name: get_default_engineer_set_id(region_id)$
-- The region's default set id; None only for a region with no loaded data at all.
SELECT id FROM engineer_sets WHERE region_id = :region_id AND kind = 'demo';

-- name: get_engineer_set(engineer_set_id)^
-- One set by id, with its region — None if there is no such set.
SELECT id, region_id, name, kind, engineers, morning_share, evening_share, seed
FROM engineer_sets
WHERE id = :engineer_set_id;

-- name: insert_default_engineer_set(region_id, engineers, morning_share, evening_share, seed)$
-- The region's first load creates this once; later loads find it already there.
INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share, evening_share, seed)
VALUES (:region_id, 'default', 'demo', :engineers, :morning_share, :evening_share, :seed)
RETURNING id;

-- name: insert_generated_engineer_set(region_id, name, engineers, morning_share, evening_share, seed)<!
-- POST /engineer-sets; the caller catches the unique-name-per-region violation as Conflict.
INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share, evening_share, seed)
VALUES (:region_id, :name, 'generated', :engineers, :morning_share, :evening_share, :seed)
RETURNING id;

-- name: delete_engineer_set(engineer_set_id)!
-- Runs last, after the set's plans and brigades are already gone.
DELETE FROM engineer_sets WHERE id = :engineer_set_id;
