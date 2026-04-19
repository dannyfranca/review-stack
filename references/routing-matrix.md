# Review routing matrix

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
