# Semantic slicing protocol

Use deterministic inventory as a seed only. The final review units must be semantic change slices, not directory buckets.

## Slice by changed behavior

A semantic slice is one independently reviewable behavior or risk surface, such as:

- one endpoint/route/controller action and its request/response schemas, client calls, validation, auth, and tests;
- one background job/worker/retry/idempotency path and its tests;
- one migration/schema/model/query behavior and its rollout/rollback constraints;
- one frontend flow: route/page/component tree + state/data fetching + tests;
- one public API/client/SDK/contract change;
- one shared helper/refactor used by multiple entrypoints.

## Multi-endpoint changes

If a diff changes multiple endpoints in the same folder, create one slice per endpoint unless the endpoints are trivial wrappers over the exact same changed implementation.

Example:

- `POST /invoices`: route, validator, service method, DB query, tests.
- `GET /invoices/:id`: route, authorization check, response schema, tests.
- `shared invoice helpers`: shared utility/service touched by both endpoints.

The shared helper may appear as context in endpoint slices and also as its own slice if it has behavior worth reviewing independently.

## Split large slices

Split a slice if it crosses unrelated behavior, unrelated data models, unrelated routes, or more than one independently testable risk surface.

Do not split a slice merely because it spans multiple files. Interaction bugs usually occur across files.

## Slice fields

Each semantic slice should include:

```json
{
  "id": "stable-kebab-id",
  "title": "human-readable title",
  "intent": "what behavior this slice changes",
  "entrypoints": ["route/function/job/component/schema"],
  "files": ["repo-relative files"],
  "changed_symbols": ["symbols/routes/jobs/contracts inferred from diff"],
  "context_files": ["minimal nearby callers/callees/tests/config to read for verification only"],
  "risk_tags": ["security|migration|api_contract|test|frontend|concurrency_perf|dependency|config_build_deploy|general"],
  "required_reviewers": ["review_slice_context", "review_security"],
  "suggested_tests": ["commands or test files"],
  "related_slices": ["ids that share helpers or contracts"],
  "reason": "why this slice boundary is useful"
}
```

## Context files

`context_files` are for understanding changed behavior. They are not independent review targets.

Keep them minimal and specific. If a concern in unchanged code is not introduced or materially worsened by the diff, it is out of scope for the main queue.

## Reviewer routing

Use slice `risk_tags` and changed behavior to choose specialists:

| Change signal | Required reviewers |
|---|---|
| Route/controller/API handler/client/schema/webhook | `review_contract_api`, `review_tests`, `review_slice_context` |
| Auth/session/permissions/middleware/tenant/org/account ownership | `review_security`, `review_tests`, `review_slice_context` |
| DB migration/schema/model/ORM/query/backfill/delete/export | `review_data_migration`, `review_tests`, `review_slice_context` |
| Background job/queue/retry/cache/lock/async/streaming | `review_concurrency_perf`, `review_tests`, `review_slice_context` |
| Payments/billing/user data/admin tools/audit logs | `review_security`, `review_data_migration`, `review_contract_api` |
| Frontend data fetching/form/state/routing | `review_slice_context`, `review_tests`, optionally `review_contract_api` |
| Dependency/lockfile/build/deploy/config/IaC | `review_security`, `review_concurrency_perf` where runtime risk exists |
| Test-only change | `review_tests`, one `review_diff_bug` over affected production assumptions |
| Broad refactor across subsystems | one `review_slice_context` per subsystem plus `review_final_gate` |

Always run two independent `review_diff_bug` reviewers and one `review_tests` reviewer.

## Shared files

A file may belong to multiple slices. That is expected. Avoid assigning a shared file to only one slice when different changed hunks serve different behaviors.
