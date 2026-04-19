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
  "context_files": ["nearby callers/callees/tests/config to read"],
  "risk_tags": ["security|migration|api_contract|test|frontend|concurrency_perf|dependency|config_build_deploy|general"],
  "required_reviewers": ["review_slice_context", "review_security"],
  "suggested_tests": ["commands or test files"],
  "related_slices": ["ids that share helpers or contracts"],
  "reason": "why this slice boundary is useful"
}
```

## Shared files

A file may belong to multiple slices. That is expected. Avoid assigning a shared file to only one slice when different changed hunks serve different behaviors.
