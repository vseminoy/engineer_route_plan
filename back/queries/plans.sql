-- name: delete_region_replan_events(region_id)!
-- Replan events of every plan of the region, whether the plan is the one an event
-- was applied to or the one it produced.
DELETE FROM replan_events
WHERE plan_id IN (SELECT id FROM plans WHERE region_id = :region_id)
   OR result_plan_id IN (SELECT id FROM plans WHERE region_id = :region_id);

-- name: delete_region_assignments(region_id)!
-- Plan rows of every plan of the region.
DELETE FROM assignments
WHERE plan_id IN (SELECT id FROM plans WHERE region_id = :region_id);

-- name: delete_region_plans(region_id)!
-- All plans of the region in one statement: a plan's parent is a plan of the same
-- region, and the reference is checked once the whole statement has run.
DELETE FROM plans WHERE region_id = :region_id;
