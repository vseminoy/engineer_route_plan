# Slice: front/api — codegen client and zod schemas from the OpenAPI contract

Run: 260927062026 | Task: F1
Date: 2026-09-27 | Type: config/ci | Commits: a17dbc0
Modules: front/src/api

## Business rules
None — route `config/ci` has no step 2 (rule registry), so no `R-<run>-<n>` is minted this run.

## ADDED
- `front/orval.config.ts` — two orval targets off `specs/openapi.yaml` + `common.yaml`: `client`
  (`client: 'fetch'` + `schemas`) and `zod` (`client: 'zod'`, `override.zod.strict` on every input
  location, `dateTimeOptions: { local: true }`, `version: 4`).
- `front/src/api/generated/` (fetch client, per-status-code response types, `components.schemas`
  types) and `front/src/api/generated/zod/` (request-side zod schemas) — committed, generated,
  excluded from hand editing by orval's own file header.
- `npm run gen:api` (`front/package.json`); `Makefile` targets `front-dev`, `front-lint`,
  `front-test`, `gen-front`, `check-front` (regenerate, assert no diff, typecheck, test), `gen`
  (backend `gen-api` + `gen-front`).
- `zod@^4.6.5` (dependency), `orval@^8.38.0` (devDependency) in `front/package.json`.

## MODIFIED
None.

## REMOVED
None.

## Decisions
- `override.zod.version: 4` pinned explicitly rather than left at orval's default `'auto'`, so the
  generated syntax (`z.strictObject`) does not depend on which `zod` version happens to be resolved
  in `front/node_modules` at generation time.
- `mode: 'split'` on both orval targets, not `'tags-split'`: `specs/openapi.yaml` declares no
  OpenAPI `tags` yet, so tag-based splitting would bucket every operation under one default
  directory and add a path segment for no benefit.
- No GitHub Actions workflow added, and `.claude/hooks/pre-commit-gate.sh` left untouched: the
  repository has no CI at all and the gate is backend-only by construction; per the pipeline's own
  step 19 guidance both are project-level decisions to offer the user separately, not a rider on
  this task.

## Rejected alternatives
- `override.zod.version: 'auto'` — rejected, see Decisions (non-deterministic across `zod` bumps).
- `mode: 'tags-split'` for the orval outputs — rejected, see Decisions (no tags in the contract).

## ADR
None.
