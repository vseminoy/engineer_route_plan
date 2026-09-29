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

-- name: insert_running_plan(region_id, plan_date, algorithm, created_at)$
-- Queues a build: a plan row with no routes yet. Returns its id.
INSERT INTO plans (region_id, plan_date, algorithm, status, created_at)
VALUES (:region_id, :plan_date, :algorithm, 'running', :created_at)
RETURNING id;

-- name: mark_plan_done(plan_id)!
-- The build finished; assignment rows are inserted in the same transaction.
UPDATE plans SET status = 'done' WHERE id = :plan_id;

-- name: mark_plan_failed(plan_id, failed_reason)!
-- The build did not finish; no assignment rows exist for this plan.
UPDATE plans SET status = 'failed', failed_reason = :failed_reason WHERE id = :plan_id;

-- name: insert_assignments(plan_id, ticket_id, engineer_id, sequence_no, planned_arrival, travel_time_min, travel_distance_m, unassigned_reason, explanation)*!
-- One row per open ticket of the plan's region: assigned (engineer_id and the rest of the
-- route fields) or not (unassigned_reason), never both.
INSERT INTO assignments (plan_id, ticket_id, engineer_id, sequence_no, planned_arrival,
                         travel_time_min, travel_distance_m, unassigned_reason, explanation)
VALUES (:plan_id, :ticket_id, :engineer_id, :sequence_no, :planned_arrival,
        :travel_time_min, :travel_distance_m, :unassigned_reason, :explanation);

-- name: get_plan(plan_id)^
-- The plan row by id; None if there is no such plan.
SELECT id, region_id, algorithm, status, failed_reason
FROM plans
WHERE id = :plan_id;

-- name: list_plan_assignments(plan_id)
-- Rows of a `done` plan, in ticket id order, with the ticket's duration: idle time of a
-- brigade is its shift minus the summed travel and on-site time of its visits, and the
-- row itself does not carry on-site time.
SELECT a.ticket_id, a.engineer_id, a.sequence_no, a.planned_arrival, a.travel_time_min,
       a.travel_distance_m, a.unassigned_reason, a.explanation, t.duration_min
FROM assignments a
JOIN tickets t ON t.id = a.ticket_id
WHERE a.plan_id = :plan_id
ORDER BY a.ticket_id;
