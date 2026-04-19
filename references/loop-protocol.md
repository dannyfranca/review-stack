# Loop edge cases

`SKILL.md` owns the canonical review lifecycle. Read this file only for edge cases that are easy to mishandle during a long-running or interrupted session.

## Session recovery

- Reuse the existing `REVIEW_DIR` when resuming an interrupted run in the same worktree.
- Inspect `state.json`, `inventory.json`, and `semantic-slices.json` before spawning a new review wave.
- Do not restart from loop 1 unless the existing session files are missing or clearly unusable.
- If `state.json` is corrupt but the rest of the session is intact, repair the minimum required fields and preserve the same `session_id`.

## Blocked and manual-decision outcomes

Use `blocked` when validation cannot run safely, dependencies or credentials are unavailable, or the diff cannot be interpreted with confidence.

Use `needs_manual_decision` when the remaining high-severity items depend on human judgment, such as:

- intentional API or product behavior changes;
- security-policy tradeoffs;
- migration/deploy risk acceptance;
- architecture or ownership boundaries;
- test expectations that depend on intended behavior.

Keep those items in `$REVIEW_DIR/manual-review.md`. Do not continue the automated fix loop once only manual-decision items remain.

## Convergence edge cases

- If deterministic checks cannot run, document exactly why before stopping.
- If two consecutive loops produce only rejected, duplicate, `question`, `nit`, or `pre_existing` outcomes, stop instead of forcing another broad wave.
- If a fix lands, re-run the narrowest relevant checks and re-review the affected semantic slice before deciding whether a full extra loop is necessary.
- If `max_loops` is reached, stop cleanly, record the reason, and leave the remaining confirmed queue intact.

## Dedupe edge cases

- `review-dedupe.py` can suggest overlap, but it never decides the canonical queue.
- When two findings touch the same file but describe different entrypoints, failure modes, or fix directions, keep them separate.
- When uncertain whether two findings share one root cause, prefer separate items or move the merge decision into manual review.
