-- name: upsert_region(code, name, office_address, office_lon, office_lat)<!
-- Creates the region or refreshes its name and office by code; returns its id.
-- Runs first in the transaction that replaces a region's data: the row lock it
-- takes makes a concurrent load of the same region wait until this one commits.
INSERT INTO regions (code, name, office_address, office_geom)
VALUES (:code, :name, :office_address,
        ST_SetSRID(ST_MakePoint(:office_lon, :office_lat), 4326))
ON CONFLICT ON CONSTRAINT ux_regions__code DO UPDATE
    SET name = EXCLUDED.name,
        office_address = EXCLUDED.office_address,
        office_geom = EXCLUDED.office_geom
RETURNING id;

-- name: get_region_id(code)$
-- Id of the region with this code; none until the region's data is loaded for the first time.
SELECT id FROM regions WHERE code = :code;
