# Module: front/src/api

Updated: 2026-09-27 | Slice: 260927-front-api-codegen

## Purpose
API layer of the frontend: a client and TypeScript types generated from the backend contract, plus
zod schemas for client-side form/parameter validation before a request is sent.

## Entry points
Not HTTP handlers — one generated function per contract `operationId`, all in
`front/src/api/generated/engineerRoutePlanAPI.ts` (e.g. `listRegions`, `uploadRegionData`,
`listTickets`, `changeTicketStatus`). Each function's return type is a union typed per status code;
only `400` carries a body (`ValidationError`), matching the contract.

## Layers and key types
- codegen config: `front/orval.config.ts` — two orval targets, both fed by
  `../specs/openapi.yaml` (`common.yaml` allowed as an external `$ref` via
  `input.parserOptions.externalRefs.allow`):
  - `client` → `client: 'fetch'` + `schemas` → `front/src/api/generated/` (client functions,
    `front/src/api/generated/schemas/*.ts` for `components.schemas` types, incl. `ValidationError`,
    `FieldError`).
  - `zod` → `client: 'zod'` → `front/src/api/generated/zod/engineerRoutePlanAPI.ts` (request-side
    validation schemas: path/query/header/body per operation).
- existing hand-written layer, untouched by this module: `front/src/api/{types.ts,endpoints.ts,client.ts}`
  — still the one actually used by the app; nothing in `front/src` imports `generated/` yet.

## Data
N/A — no direct data access; this module only shapes HTTP request/response types.

## Consumers and links
None yet. `front/src/api/client.ts` (error handling) and the TanStack Query hooks under
`front/src/queries/` are the intended consumers, wired up starting the changeset that replaces the
hand-written API layer.

## Invariants and pitfalls
- **Generated files carry a "Do not edit manually" header** — hand edits are silently lost on the
  next `make gen-front`. Change `specs/openapi.yaml`/`common.yaml` or `front/orval.config.ts`
  instead, then regenerate.
- **`make check-front` is what catches contract drift** — it regenerates and then runs
  `git diff --exit-code front/src/api/generated`; a spec change committed without regenerating in
  the same commit fails this target, not CI (there is no CI workflow in this repository yet).
- **The zod target only emits request-side schemas** (param/query/header/body) — `override.zod.generate`
  defaults to no response schemas, so `ValidationError`/`FieldError` have no zod counterpart; only
  the `client` target's TS types cover them. Do not expect a zod schema for a response body.
- **`override.zod.version: 4` is pinned explicitly** — without it orval infers the target Zod
  version from the installed `zod` package (`'auto'`), so a `zod` dependency bump could silently
  change generated syntax (`z.strictObject` vs `.strict()`).
- **`LocalDateTime`/`LocalTime` (`common.yaml`) are plain pattern-strings, not `format: date-time`/
  `date`** — `override.zod.dateTimeOptions.local` therefore affects nothing yet; it activates once
  an operation declares `format: date`/`date-time` (planned for the plan-build endpoint).

## Business rules in force
None — route `config/ci` has no step 2 (rule registry); nothing here to give an `R-<run>-<n>` to.

## Known tech debt
- No GitHub Actions (or other CI) exists in this repository — `make check-front` is the only gate,
  run by hand or via the pre-commit hook. Noted at slice 260927-front-api-codegen; not fixed there
  (out of scope — a project-level decision, not a rider on that task).
- `.claude/hooks/pre-commit-gate.sh` never runs `make check-front` — it only gates `back/`. Noted at
  slice 260927-front-api-codegen; extending it needs the user's go-ahead (offered, not yet taken).
