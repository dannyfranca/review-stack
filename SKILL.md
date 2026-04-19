---
name: review-stack
description: Explicit iterative local code-review workflow for Codex. Use when the user asks to review uncommitted changes, review a branch against a base, run multi-agent review, keep reviewing until convergence, or optionally fix confirmed review findings.
---

# Review Stack

Run a high-signal local review loop that minimizes human scheduling, dedupe, and re-review work. Optimize for correctness and human attention, not token use.

This skill owns all review-specific prompting. Do not rely on repository root review instructions except for general repository conventions and validation commands.

## Mandatory references

At the start of a review-stack run, read these files from this skill directory:

- `references/review-policy.md`
- `references/semantic-slicing.md`
- `references/routing-matrix.md`
- `references/loop-protocol.md`
- `references/output-contract.md`

Use `schemas/finding.schema.json` for reviewer outputs and `schemas/loop-state.schema.json` for durable state. Use `assets/final-report-template.md` for the final human-facing report. Use `assets/state-template.json` when initializing state manually.

## Inputs

Infer these from the user request or environment:

- `base`: default `origin/main`, then `main`, then merge-base with the upstream branch.
- `mode`: `audit` by default; `fix` only when the user asks to fix or says to keep iterating/fixing automatically.
- `scope`: default all branch and working-tree changes.
- `max_loops`: default 6 as a safety guard. Stop earlier when convergence criteria are met.

## State directory

Create and maintain `.review/`:

```text
.review/
  state.json                              # durable loop state
  inventory.json                          # changed files, stats, risk tags, diff paths
  slices.preliminary.json                 # deterministic seed slices
  semantic-slices.json                    # final semantic review slices
  full.diff                               # full branch/staged/unstaged diff context
  slice-diffs/<slice-id>.diff             # per-slice diff context when available
  raw-findings/loop-<n>/<agent>.json      # raw reviewer output
  verified/loop-<n>/                      # verifier verdicts
  deduped-findings.json                   # canonical queue after merge/dedupe
  resolved-findings.json                  # issues fixed in this run
  manual-review.md                        # ambiguous/product/security decisions for the user
  reports/loop-<n>.md                     # loop summaries
  final-report.md                         # final human-facing report
```

Never use `.review/` findings as proof by themselves. Treat them as working memory that must be rechecked against the current code.

## Review loop

Execute this loop until convergence:

1. **Inventory**
   - Run `python3 .agents/skills/review-stack/scripts/review-inventory.py --base <base> --mode <mode> --max-loops <max_loops>`.
   - Read `.review/inventory.json`, `.review/slices.preliminary.json`, and `.review/full.diff`.
   - Run `python3 .agents/skills/review-stack/scripts/review-status.py` to inspect existing loop state if `.review/` already exists.
   - If the script cannot run, build equivalent inventory manually and write the same files.

2. **Semantic mapping**
   - Spawn `review_mapper` before any reviewer wave.
   - Give it `.review/inventory.json`, `.review/slices.preliminary.json`, `.review/full.diff`, and `references/semantic-slicing.md`.
   - It must produce `.review/semantic-slices.json`.
   - Semantic slices must be based on changed behavior, entrypoint, route, job, migration, contract, frontend flow, or shared helper. They must not be limited to file-name buckets.
   - If multiple endpoints changed under the same directory, create one semantic slice per endpoint or API action unless they are the same behavior.
   - Allow files to appear in multiple slices when shared helpers or contracts connect behaviors.
   - If `review_mapper` is unavailable, emulate it in the parent thread and write `.review/semantic-slices.json` manually.

3. **Deterministic gates**
   - Discover cheap validation commands from repo scripts/config and from `semantic-slices.json.suggested_tests`.
   - Run cheap safe checks first: diff check, typecheck, lint, focused tests.
   - Store results in `.review/state.json`.
   - Do not report issues that are already fully covered by deterministic gates unless they expose behavior risk.

4. **Parallel review wave**
   - Spawn subagents explicitly. Use the custom agents in `.codex/agents` when available; otherwise emulate the same roles.
   - Always run two independent `review_diff_bug` reviewers over the whole diff.
   - Always run `review_tests` over the full diff and test changes.
   - Run one `review_slice_context` reviewer per semantic slice from `.review/semantic-slices.json`, capped by `agents.max_threads`; batch remaining slices if needed.
   - Trigger specialists from each slice's `required_reviewers` and `references/routing-matrix.md`.
   - Ask each reviewer to return JSON matching `schemas/finding.schema.json`.
   - Save outputs under `.review/raw-findings/loop-<n>/`.

5. **Verification wave**
   - For every blocking/important candidate, spawn `review_verifier`.
   - The verifier must try to reject the finding first.
   - Confirm only findings that are introduced by the diff, concrete, reachable or plausibly production-relevant, and supported by code evidence.
   - Save verifier output under `.review/verified/loop-<n>/`.

6. **Aggregation and dedupe**
   - Run `python3 .agents/skills/review-stack/scripts/review-dedupe.py` when raw JSON exists.
   - Use `review_aggregator` to merge duplicates by root cause, drop rejected findings, downgrade speculative findings, and produce the canonical queue.
   - Keep ambiguous product/security/architecture questions in `.review/manual-review.md`; do not send them into the fix loop.

7. **Fix phase**
   - If `mode=audit`, do not edit production files. Go to convergence check.
   - If `mode=fix`, fix only confirmed blocking/important findings.
   - Use `review_fixer` for one issue or tightly-related issue cluster at a time.
   - Prefer isolated worktrees when practical. If working in the current tree, avoid concurrent fixers touching overlapping files.
   - After each fix, run the narrowest relevant checks and re-review the affected semantic slice.
   - Mark resolved findings in `.review/resolved-findings.json` with evidence and tests run.

8. **Convergence check**
   - Start another full loop if any confirmed blocking/important finding remains.
   - Start another full loop if fixes were applied in this loop.
   - Stop when a full review wave produces zero new confirmed blocking/important findings and deterministic gates are passing or documented.
   - If two consecutive loops produce only rejected/duplicate/question/nit findings, stop and write the final report.
   - If `max_loops` is reached, stop and clearly mark remaining risk.

9. **Final gate**
   - Spawn `review_final_gate` over the final full diff.
   - Incorporate only new confirmed findings.
   - Run `python3 .agents/skills/review-stack/scripts/review-status.py` and write the status summary into the final report.
   - Write `.review/final-report.md` using `assets/final-report-template.md`.

## Output discipline

The final response to the user should not dump raw subagent output. Return:

- final verdict;
- blocking/important queue, deduped;
- what was fixed, if anything;
- remaining manual decisions;
- deterministic checks run;
- path to `.review/final-report.md`.

## Hard constraints

- Do not commit code.
- Do not stage files.
- Do not rewrite history.
- Do not report unverified speculative issues as blocking.
- Do not keep looping on nits or unresolved product questions.
- Preserve `.review/` across loops.
