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

-- name: delete_engineer_set_replan_events(engineer_set_id)!
-- Replan events of every plan of the set, whether the plan is the one an event was
-- applied to or the one it produced. Runs before delete_engineer_set_assignments.
DELETE FROM replan_events
WHERE plan_id IN (SELECT id FROM plans WHERE engineer_set_id = :engineer_set_id)
   OR result_plan_id IN (SELECT id FROM plans WHERE engineer_set_id = :engineer_set_id);

-- name: delete_engineer_set_assignments(engineer_set_id)!
DELETE FROM assignments
WHERE plan_id IN (SELECT id FROM plans WHERE engineer_set_id = :engineer_set_id);

-- name: delete_engineer_set_plans(engineer_set_id)!
-- All plans of the set in one statement, same reasoning as delete_region_plans.
DELETE FROM plans WHERE engineer_set_id = :engineer_set_id;

-- name: delete_plan_tree_replan_events(plan_id)!
-- Replan events of plan_id and every plan replanned from it, directly or through a
-- chain (WITH RECURSIVE over parent_plan_id), whether the plan is the one an event was
-- applied to or the one it produced. Runs before delete_plan_tree_assignments.
WITH RECURSIVE tree AS (
    SELECT id FROM plans WHERE id = :plan_id
    UNION ALL
    SELECT p.id FROM plans p JOIN tree t ON p.parent_plan_id = t.id
)
DELETE FROM replan_events
WHERE plan_id IN (SELECT id FROM tree) OR result_plan_id IN (SELECT id FROM tree);

-- name: delete_plan_tree_assignments(plan_id)!
-- Assignment rows of plan_id and every plan replanned from it.
WITH RECURSIVE tree AS (
    SELECT id FROM plans WHERE id = :plan_id
    UNION ALL
    SELECT p.id FROM plans p JOIN tree t ON p.parent_plan_id = t.id
)
DELETE FROM assignments
WHERE plan_id IN (SELECT id FROM tree);

-- name: delete_plan_tree(plan_id)
-- plan_id and every plan replanned from it, directly or through a chain, in one
-- statement: a plan's parent is in the same deleted set, and the reference is checked
-- once the whole statement has run — same reasoning as delete_region_plans. Returns the
-- deleted ids.
WITH RECURSIVE tree AS (
    SELECT id FROM plans WHERE id = :plan_id
    UNION ALL
    SELECT p.id FROM plans p JOIN tree t ON p.parent_plan_id = t.id
)
DELETE FROM plans WHERE id IN (SELECT id FROM tree)
RETURNING id;

-- name: insert_running_plan(region_id, engineer_set_id, plan_date, algorithm, created_at)^
-- Queues a build: a plan row with no routes yet, status=running, name='' — set to its
-- final value right after by update_plan_name, once this row's id is known (see
-- repository.plans.insert_running_plan; the name embeds the id, which Postgres only
-- assigns at insert time). None instead of a row if a concurrent build already holds
-- the active baseline slot for this (engineer_set_id, plan_date) — see
-- ux_plans__active_baseline_per_set_date.
INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status, created_at, name)
VALUES (:region_id, :engineer_set_id, :plan_date, :algorithm, 'running', :created_at, '')
ON CONFLICT (engineer_set_id, plan_date)
    WHERE algorithm = 'baseline_fcfs' AND status IN ('running', 'done')
    DO NOTHING
RETURNING id;

-- name: get_latest_baseline_plan(engineer_set_id, plan_date)^
-- The most recent baseline_fcfs plan for this (engineer_set_id, plan_date), any status —
-- at most one in status running or done can exist at a time
-- (ux_plans__active_baseline_per_set_date); a failed one may coexist only until
-- POST /plan/build next deletes it and builds fresh. None if there is no such plan yet.
SELECT id, status
FROM plans
WHERE engineer_set_id = :engineer_set_id AND plan_date = :plan_date
      AND algorithm = 'baseline_fcfs'
ORDER BY created_at DESC
LIMIT 1;

-- name: update_plan_name(plan_id, name)!
-- Overwrites a plan's name, whatever it was set to before (automatic or a previous
-- rename) and whatever the plan's status — build state is untouched.
UPDATE plans SET name = :name WHERE id = :plan_id;

-- name: mark_plan_done(plan_id)!
-- The build finished; assignment rows are inserted in the same transaction.
UPDATE plans SET status = 'done' WHERE id = :plan_id;

-- name: mark_plan_failed(plan_id, failed_reason)!
-- The build did not finish; no assignment rows exist for this plan.
UPDATE plans SET status = 'failed', failed_reason = :failed_reason WHERE id = :plan_id;

-- name: sweep_running_plans(failed_reason)
-- Every plan left `running` across all regions: the process that was building it stopped
-- before writing an outcome (a backend restart, graceful or not). Closes them all in one
-- statement and returns the ids for logging; called once at startup, before the app
-- accepts requests.
UPDATE plans SET status = 'failed', failed_reason = :failed_reason
WHERE status = 'running'
RETURNING id;

-- name: insert_assignments(plan_id, ticket_id, engineer_id, sequence_no, planned_arrival, travel_time_min, travel_distance_m, unassigned_reason, explanation)*!
-- One row per open ticket of the plan's region: assigned (engineer_id and the rest of the
-- route fields) or not (unassigned_reason), never both.
INSERT INTO assignments (plan_id, ticket_id, engineer_id, sequence_no, planned_arrival,
                         travel_time_min, travel_distance_m, unassigned_reason, explanation)
VALUES (:plan_id, :ticket_id, :engineer_id, :sequence_no, :planned_arrival,
        :travel_time_min, :travel_distance_m, :unassigned_reason, :explanation);

-- name: list_plans_by_region(region_id)
-- Все планы региона (любой статус), по убыванию created_at — сначала новые.
SELECT p.id, p.name, r.code AS region_code, p.engineer_set_id, p.plan_date, p.algorithm,
       p.status, p.failed_reason, p.parent_plan_id, p.created_at
FROM plans p
JOIN regions r ON r.id = p.region_id
WHERE p.region_id = :region_id
ORDER BY p.created_at DESC;

-- name: list_plans_by_engineer_set(engineer_set_id)
-- Планы одного набора бригад (любой статус), по убыванию created_at — та же форма
-- строки, что list_plans_by_region, для набора вместо целого региона.
SELECT p.id, p.name, r.code AS region_code, p.engineer_set_id, p.plan_date, p.algorithm,
       p.status, p.failed_reason, p.parent_plan_id, p.created_at
FROM plans p
JOIN regions r ON r.id = p.region_id
WHERE p.engineer_set_id = :engineer_set_id
ORDER BY p.created_at DESC;

-- name: get_plan(plan_id)^
-- The plan row by id, with its region's code; None if there is no such plan.
SELECT p.id, p.name, p.region_id, r.code AS region_code, p.engineer_set_id, p.plan_date,
       p.algorithm, p.status, p.failed_reason
FROM plans p
JOIN regions r ON r.id = p.region_id
WHERE p.id = :plan_id;

-- name: get_plan_summary(plan_id)^
-- A plan in the same row shape as list_plans_by_region/list_plans_by_engineer_set, by id
-- instead of by region/set — used by PATCH /plan/{plan_id} to answer with the plan's
-- current summary right after renaming it. None if there is no such plan.
SELECT p.id, p.name, r.code AS region_code, p.engineer_set_id, p.plan_date, p.algorithm,
       p.status, p.failed_reason, p.parent_plan_id, p.created_at
FROM plans p
JOIN regions r ON r.id = p.region_id
WHERE p.id = :plan_id;

-- name: insert_replanned_plan(region_id, engineer_set_id, plan_date, algorithm, parent_plan_id, created_at)$
-- A plan produced by one replan event: done from the moment it exists, with its
-- assignment rows inserted in the same transaction — replan is synchronous, unlike
-- POST /plan/build, so there is no running state to pass through. engineer_set_id is
-- always the parent plan's own — replan never changes a plan's set. name='' here — set
-- to "План №{id}" right after by update_plan_name, once this row's id is known (see
-- repository.plans.insert_replanned_plan).
INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,
                    parent_plan_id, created_at, name)
VALUES (:region_id, :engineer_set_id, :plan_date, :algorithm, 'done',
        :parent_plan_id, :created_at, '')
RETURNING id;

-- name: list_plan_assignments(plan_id)
-- Rows of a `done` plan, in ticket id order, with the ticket's duration and window start:
-- idle time of a brigade is the gap between departing for its first visit and finishing
-- its last, minus the summed travel and on-site time in between — the row itself does
-- not carry on-site time or the window (needed to clamp the last visit's arrival if it
-- is still waiting for its own window to open).
SELECT a.ticket_id, a.engineer_id, a.sequence_no, a.planned_arrival, a.travel_time_min,
       a.travel_distance_m, a.unassigned_reason, a.explanation, t.duration_min, t.window_start
FROM assignments a
JOIN tickets t ON t.id = a.ticket_id
WHERE a.plan_id = :plan_id
ORDER BY a.ticket_id;
