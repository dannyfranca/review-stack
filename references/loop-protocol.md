# Review-stack loop protocol

## Canonical lifecycle

1. Build inventory.
2. Run deterministic checks.
3. Run broad reviewers.
4. Run routed specialist reviewers.
5. Verify candidates.
6. Dedupe by root cause.
7. Fix confirmed issues if requested.
8. Re-review affected slices.
9. Run final full-diff gate.
10. Write final report.

## Convergence criteria

Stop when all are true:

- no confirmed `blocking` or `important` findings remain;
- the last full review loop produced zero new confirmed root causes;
- deterministic checks pass, are not applicable, or are explicitly documented as not run;
- remaining items are only `nit`, `question`, `pre_existing`, `rejected`, or `duplicate`.

Stop with `needs_manual_decision` when the only remaining high-severity items are product/security/architecture decisions that cannot be resolved from code.

Stop with `blocked` when validation cannot run, dependencies are unavailable, or the diff cannot be understood safely.

## Root-cause dedupe key

Merge findings when these fields describe the same underlying problem:

- category;
- failure mode;
- affected symbol/API/route/job/schema;
- primary changed file;
- overlapping line range or same call path;
- same minimal fix direction.

Do not merge separate bugs just because they appear in the same file.

## Manual-review inbox

Use `.review/manual-review.md` for items requiring human judgment:

- intentional API break or product behavior change;
- uncertain security policy tradeoff;
- migration/deploy risk acceptance;
- unclear ownership or architecture boundary;
- test expectation depends on intended behavior.

Manual-review items do not block the automated fix loop unless they are confirmed security/data risks.
