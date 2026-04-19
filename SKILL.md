---
name: review-stack
description: Explicit iterative local code-review workflow for Codex. Use when the user asks to review uncommitted changes, review a branch against a base, run multi-agent review, keep reviewing until convergence, or optionally fix confirmed review findings.
---

# Review Stack

Run a high-signal local review loop that minimizes human scheduling, duplicate triage, and repeated whole-diff review work. Optimize for correctness and human attention, not token use.

This skill owns all review-specific prompting. Keep root `AGENTS.md` minimal and do not rely on always-loaded repo instructions for review policy.

## Script path rule

Do not assume this skill is installed at `.agents/skills/review-stack`. At the start of a run, resolve `SKILL_DIR` once:

```bash
if [ -n "${REVIEW_STACK_SKILL_DIR:-}" ]; then
  SKILL_DIR="$REVIEW_STACK_SKILL_DIR"
elif [ -f ".agents/skills/review-stack/SKILL.md" ]; then
  SKILL_DIR=".agents/skills/review-stack"
elif [ -f "$HOME/.codex/skills/review-stack/SKILL.md" ]; then
  SKILL_DIR="$HOME/.codex/skills/review-stack"
else
  echo "Cannot locate review-stack skill directory" >&2
  exit 2
fi
```

Run helper scripts through `$SKILL_DIR/scripts/...`. If a script cannot run, perform the same step manually and write the same output files.

## Reference loading

Read these files at the start of every review-stack run:

- `references/review-policy.md`
- `references/semantic-slicing.md`
- `references/routing-matrix.md`

Read these files only when the phase needs them:

- `references/loop-protocol.md` for interrupted-session recovery, blocked/manual-decision handling, or convergence/dedupe edge cases.
- `references/output-contract.md` when writing or validating `semantic-slices.json`, reviewer JSON, verifier JSON, `deduped-findings.json`, or the final report structure.

Use `schemas/finding.schema.json` for reviewer outputs and `schemas/loop-state.schema.json` for durable state. Use `assets/final-report-template.md` for the final human-facing report. `assets/state-template.json` is used by `review-inventory.py` and by manual state initialization.

## Preferred orchestration

Prefer `python3 "$SKILL_DIR/scripts/review-run.py" ...` as the thin control surface for session bootstrap, loop bookkeeping, and status transitions.

Use the lower-level helper scripts directly only when:

- `review-run.py` cannot run;
- you need a primitive that the wrapper does not expose; or
- you are manually repairing a partially written session.

`review-run.py` is not a reviewer. It only coordinates `review-inventory.py`, `review-state.py`, and `review-status.py`.

## Inputs

Infer these from the user request or environment:

- `base`: default `origin/main`, then `main`, then merge-base with the upstream branch.
- `mode`: `audit` by default; `fix` only when the user asks to fix or says to keep iterating/fixing automatically.
- `scope`: default all branch and working-tree changes.
- `max_loops`: default 6 as a safety guard. Stop earlier when convergence criteria are met.

## Session directory

Resolve `REVIEW_DIR` once per run. If the user or environment already provides a directory, keep using it. Otherwise let `review-inventory.py` allocate a default session directory under `.review-sessions/<session-id>`. Reuse that same `REVIEW_DIR` for every helper invocation in the run.

Support multiple concurrent `audit` sessions only when they use different `REVIEW_DIR` values. Do not run concurrent `fix` sessions in the same worktree; use separate git worktrees for parallel fix work.

Create and maintain `REVIEW_DIR`:

```text
<review-dir>/
  state.json                              # durable loop state
  inventory.json                          # changed files, stats, risk tags, diff paths
  slices.preliminary.json                 # deterministic seed slices, never final review slices
  semantic-slices.json                    # final semantic review slices
  full.diff                               # full branch/staged/unstaged/untracked diff context
  slice-diffs/<slice-id>.diff             # per-preliminary-slice seed diff context when available
  raw-findings/loop-<n>/<agent>.json      # raw reviewer output
  verified/loop-<n>/                      # verifier verdicts
  dedupe-candidates.json                  # optional non-authoritative duplicate-pair hints
  deduped-findings.json                   # authoritative canonical queue from review_aggregator
  resolved-findings.json                  # issues fixed in this run
  manual-review.md                        # ambiguous/product/security decisions for the user
  reports/loop-<n>.md                     # loop summaries
  final-report.md                         # final human-facing report
```

Never use `REVIEW_DIR` findings as proof by themselves. Treat them as working memory that must be rechecked against the current code. The helper scripts are bookkeeping/context-packaging utilities; they are not reviewers and their outputs are not authoritative about correctness.

## Review loop

Execute this loop until convergence:

1. **Inventory**
   - Resolve `SKILL_DIR` using the script path rule.
   - Prefer `python3 "$SKILL_DIR/scripts/review-run.py" prepare --base <base> --mode <mode> --max-loops <max_loops> [--review-dir "$REVIEW_DIR"]`.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-inventory.py" --base <base> --mode <mode> --max-loops <max_loops> [--review-dir "$REVIEW_DIR"]`.
   - Capture `review_dir` and `session_id` from the script output when `REVIEW_DIR` was not preselected, then reuse that exact `REVIEW_DIR` for the rest of the run.
   - Read `$REVIEW_DIR/inventory.json`, `$REVIEW_DIR/slices.preliminary.json`, and `$REVIEW_DIR/full.diff`.
   - Run `python3 "$SKILL_DIR/scripts/review-run.py" status --review-dir "$REVIEW_DIR"` to inspect existing loop state if the session directory already exists.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-status.py" --review-dir "$REVIEW_DIR"`.
   - Inventory is non-destructive: it writes only `REVIEW_DIR`, excludes review-state directories and generated/vendor paths from scope, and includes synthetic diff blocks for text untracked files.
   - If the script cannot run, build equivalent inventory manually and write the same files.

2. **Loop bookkeeping**
   - Start each full loop with `python3 "$SKILL_DIR/scripts/review-run.py" start-loop --review-dir "$REVIEW_DIR" --note "<short loop intent>"`.
   - Use `record-check`, `finish-loop`, and `stop` through `review-run.py` to keep `$REVIEW_DIR/state.json` consistent.
   - If `review-state.py` cannot run, update `$REVIEW_DIR/state.json` manually using `schemas/loop-state.schema.json`.

3. **Semantic mapping**
   - Spawn `review_mapper` before any reviewer wave.
   - Give it `$REVIEW_DIR/inventory.json`, `$REVIEW_DIR/slices.preliminary.json`, `$REVIEW_DIR/full.diff`, and `$SKILL_DIR/references/semantic-slicing.md`.
   - It must produce `$REVIEW_DIR/semantic-slices.json`.
   - Semantic slices must be based on changed behavior, entrypoint, route, job, migration, contract, frontend flow, or shared helper. They must not be limited to file-name buckets.
   - If multiple endpoints changed under the same directory, create one semantic slice per endpoint or API action unless they are the same behavior.
   - Allow files to appear in multiple slices when shared helpers or contracts connect behaviors.
   - If `review_mapper` is unavailable, emulate it in the parent thread and write `$REVIEW_DIR/semantic-slices.json` manually.

4. **Deterministic gates**
   - Discover cheap validation commands from repo scripts/config and from `$REVIEW_DIR/semantic-slices.json.suggested_tests`.
   - Run cheap safe checks first: diff check, typecheck, lint, focused tests.
   - Record each check with `python3 "$SKILL_DIR/scripts/review-run.py" record-check --review-dir "$REVIEW_DIR" --command "<cmd>" --status pass|fail|skipped|unknown --note "<note>"`.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-state.py" --review-dir "$REVIEW_DIR" record-check ...`.
   - Do not report issues that are already fully covered by deterministic gates unless they expose behavior risk.

5. **Parallel review wave**
   - Spawn subagents explicitly. Use the custom agents in `.codex/agents` when available; otherwise emulate the same roles.
   - Always run two independent `review_diff_bug` reviewers over the whole diff.
   - Always run `review_tests` over the full diff and test changes.
   - Run one `review_slice_context` reviewer per semantic slice from `$REVIEW_DIR/semantic-slices.json`, capped by `agents.max_threads`; batch remaining slices if needed.
   - Trigger specialists from each slice's `required_reviewers` and `references/routing-matrix.md`.
   - Ask each reviewer to return JSON matching `schemas/finding.schema.json`.
   - Save outputs under `$REVIEW_DIR/raw-findings/loop-<n>/`.

6. **Verification wave**
   - For every blocking/important candidate, spawn `review_verifier`.
   - The verifier must try to reject the finding first.
   - Confirm only findings that are introduced by the diff, concrete, reachable or plausibly production-relevant, and supported by code evidence.
   - Save verifier output under `$REVIEW_DIR/verified/loop-<n>/`.

7. **Contextual aggregation and dedupe**
   - Run `python3 "$SKILL_DIR/scripts/review-dedupe.py" --review-dir "$REVIEW_DIR"` only when the review wave is noisy enough that pair hints may save time. The helper defaults to `blocking,important` findings and skips pair generation when fewer than 4 qualifying findings are present.
   - Treat `$REVIEW_DIR/dedupe-candidates.json` as optional hints only. It must not be used as the canonical queue, and its absence is normal when the run is small or low-overlap.
   - Use `review_aggregator` to perform contextual dedupe by root cause using raw findings, verifier outputs, code/diff context, semantic slices, and any candidate pair hints that exist.
   - `review_aggregator` writes `$REVIEW_DIR/deduped-findings.json` as the authoritative queue.
   - Keep ambiguous product/security/architecture questions in `$REVIEW_DIR/manual-review.md`; do not send them into the fix loop.

8. **Fix phase**
   - If `mode=audit`, do not edit production files. Go to convergence check.
   - If `mode=fix`, fix only confirmed blocking/important findings.
   - Use `review_fixer` for one issue or tightly-related issue cluster at a time.
   - Prefer isolated worktrees when practical. If working in the current tree, avoid concurrent fixers touching overlapping files.
   - After each fix, run the narrowest relevant checks and re-review the affected semantic slice.
   - Mark resolved findings in `$REVIEW_DIR/resolved-findings.json` with evidence and tests run.

9. **Convergence check**
   - Finish each loop with `python3 "$SKILL_DIR/scripts/review-run.py" finish-loop --review-dir "$REVIEW_DIR" --new-confirmed <n> --remaining-confirmed <n> --fixes-applied <n> --deterministic-gates-passing true|false|unknown`.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-state.py" --review-dir "$REVIEW_DIR" finish-loop ...`.
   - Start another full loop if any confirmed blocking/important finding remains.
   - Start another full loop if fixes were applied in this loop.
   - Stop when a full review wave produces zero new confirmed blocking/important findings and deterministic gates are passing or documented.
   - If two consecutive loops produce only rejected/duplicate/question/nit findings, stop and write the final report.
   - If `max_loops` is reached, stop and clearly mark remaining risk.

10. **Final gate**
   - Spawn `review_final_gate` over the final full diff.
   - Incorporate only new confirmed findings.
   - Run `python3 "$SKILL_DIR/scripts/review-run.py" status --review-dir "$REVIEW_DIR"` and write the status summary into the final report.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-status.py" --review-dir "$REVIEW_DIR"`.
   - Record stop reason with `python3 "$SKILL_DIR/scripts/review-run.py" stop --review-dir "$REVIEW_DIR" "<reason>"`.
   - If the wrapper cannot run, fall back to `python3 "$SKILL_DIR/scripts/review-state.py" --review-dir "$REVIEW_DIR" stop "<reason>"`.
   - Write `$REVIEW_DIR/final-report.md` using `assets/final-report-template.md`.

## Output discipline

The final response to the user should not dump raw subagent output. Return:

- final verdict;
- blocking/important queue, deduped;
- what was fixed, if anything;
- remaining manual decisions;
- deterministic checks run;
- path to `$REVIEW_DIR/final-report.md`.

## Hard constraints

- Do not commit code.
- Do not stage files.
- Do not rewrite history.
- Do not report unverified speculative issues as blocking.
- Do not keep looping on nits or unresolved product questions.
- Preserve `REVIEW_DIR` across loops but never review review-state directories as target code.
