# Review policy

This policy is loaded only when the `$review-stack` skill is invoked.

## Severity definitions

### Blocking
Use `blocking` only for issues likely to break production behavior, expose or corrupt data, bypass authentication or authorization, violate tenant/account isolation, make deployment/rollback unsafe, or break a public/internal API contract.

### Important
Use `important` for realistic correctness, security, data, migration, concurrency, performance, or test-adequacy issues introduced by the diff that should be fixed before merging but are not immediately production-critical.

### Nit
Use `nit` for small maintainability or readability concerns. Cap nits at five and never let them obscure higher-signal findings.

### Question
Use `question` when the issue depends on product intent, security policy, or an architectural decision that cannot be resolved from code. These go to `$REVIEW_DIR/manual-review.md`, not the automated fix loop.

### Pre-existing
Use `pre_existing` for defects not introduced by this diff. Exclude these from the blocking queue unless the diff materially worsens them.

## Do not report

- Pure formatting, lint, spelling, or naming issues.
- Type errors already covered by deterministic checks unless they indicate a real behavioral break.
- Generated files, snapshots, or lockfile churn unless they create a concrete risk.
- Broad refactor suggestions.
- Possible issues without a reachable code path or evidence.
- Style differences from personal preference.

## Always check when relevant

- New routes/controllers enforce authentication, authorization, and tenant/account scoping.
- New DB queries include the correct caller, tenant, org, account, or ownership constraints.
- Migrations are backward-compatible with rolling deploys and have a rollback/forward-fix story.
- New logs do not expose PII, tokens, request bodies, or secrets.
- External calls handle timeout, retry, idempotency, and error semantics.
- Background jobs are idempotent and safe under retries/concurrency.
- API response/request contracts are compatible or intentionally versioned.
- Tests prove the new behavior and the most important failure modes.

## Finding quality bar

A blocking or important finding must include:

- concrete changed code path;
- why the issue is introduced or materially worsened by this diff;
- affected file, line, symbol, route, job, schema, or contract;
- failure mode;
- minimal fix direction;
- verification path.

If any of those are missing, downgrade to `question`, `nit`, or reject it during verification.


## Contextual dedupe

Duplicate detection requires reading the actual code path and failure mode. Static pair hints may surface useful overlap, but the canonical review queue must be decided by `review_aggregator`. If two findings mention the same file but different entrypoints, line ranges, failure modes, or minimal fixes, keep them separate.
