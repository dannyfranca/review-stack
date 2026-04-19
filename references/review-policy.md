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

A finding can still be real and important yet belong in `question` when the available remediation would intentionally remove or narrow supported behavior. In that case the skill should preserve the warning, but hand the decision to a human instead of auto-fixing.

### Pre-existing
Use `pre_existing` for defects not introduced by this diff. Exclude these from the blocking queue unless the diff materially worsens them.

## Do not report

- Pure formatting, lint, spelling, or naming issues.
- Type errors already covered by deterministic checks unless they indicate a real behavioral break.
- Generated files, snapshots, or lockfile churn unless they create a concrete risk.
- Broad refactor suggestions.
- Possible issues without a reachable code path or evidence.
- Unchanged-code issues discovered while reading context unless the diff introduced or materially worsened them.
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

## Breaking-change guardrail

Route the item to `question` plus manual review instead of auto-fixing when any of these are true and the intent is not explicit:

- the fix would remove or materially narrow an existing feature, fallback, or offline path;
- the fix would tighten auth, org, tenant, or account behavior in a way that could invalidate an intentional workflow;
- the fix would change a public or internal contract rather than repairing an accidental regression;
- existing tests fail because they encode the current supported behavior, and passing them would require changing those expectations instead of restoring behavior.

Manual review should describe the candidate break clearly enough for a human owner to decide whether to keep the feature, redesign it, or accept the break.

## Scope guardrail

Review changed behavior, not the whole repository.

- You may read unchanged files as context to understand a changed path.
- Report a finding only when the diff introduced or materially worsened it, either in changed code directly or through a changed path that newly exposes unchanged code.
- If the issue would exist without this diff, reject it or classify it as `pre_existing` instead of carrying it into the queue.

## Finding quality bar

A blocking or important finding must include:

- concrete changed code path;
- why the issue is introduced or materially worsened by this diff;
- affected file, line, symbol, route, job, schema, or contract;
- failure mode;
- minimal fix direction;
- verification path.

If any of those are missing, downgrade to `question`, `nit`, or reject it during verification.

If the minimal fix direction is itself product-breaking or test-breaking, keep the evidence but downgrade the queue item to `question` until a human confirms intent.


## Contextual dedupe

Decide duplicates from code path and failure mode, not filename overlap. If two findings differ in entrypoint, line range, failure mode, or minimal fix, keep them separate.
