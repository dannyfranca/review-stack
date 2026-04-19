#!/usr/bin/env python3
"""Summarize review-stack state for humans and the parent agent.

Purpose
-------
This script is a read-only status helper. It does not decide whether findings
are valid; it reports counts and key fields from the selected review directory so the orchestrator
can quickly understand convergence state without rereading all raw JSON.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Sequence


def read_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"
    if not isinstance(data, dict):
        return None, "json root is not an object"
    return data, None


def count_markdown_items(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("- ") or line.startswith("### "):
            count += 1
    return count


def bucket_count(data: dict | None, name: str) -> int:
    if not data:
        return 0
    value = data.get(name, [])
    return len(value) if isinstance(value, list) else 0


def collect_status(review_dir: Path) -> Dict[str, Any]:
    state, state_error = read_json(review_dir / "state.json")
    inventory, inventory_error = read_json(review_dir / "inventory.json")
    preliminary, preliminary_error = read_json(review_dir / "slices.preliminary.json")
    semantic, semantic_error = read_json(review_dir / "semantic-slices.json")
    dedupe_candidates, dedupe_candidates_error = read_json(review_dir / "dedupe-candidates.json")
    deduped, deduped_error = read_json(review_dir / "deduped-findings.json")
    if dedupe_candidates_error == "missing":
        dedupe_candidates_error = None

    raw_files = list((review_dir / "raw-findings").glob("**/*.json")) if (review_dir / "raw-findings").exists() else []
    verified_files = list((review_dir / "verified").glob("**/*.json")) if (review_dir / "verified").exists() else []

    return {
        "session": {
            "review_dir": str(review_dir),
            "session_id": (state or {}).get("session_id") or (inventory or {}).get("session_id"),
            "state_review_dir": (state or {}).get("review_dir"),
            "repo_root": (state or {}).get("repo_root") or (inventory or {}).get("repo_root"),
            "head_sha": (state or {}).get("head_sha") or (inventory or {}).get("head_sha"),
        },
        "state": {
            "present": state is not None,
            "error": state_error,
            "base": state.get("base") if state else None,
            "mode": state.get("mode") if state else None,
            "current_loop": state.get("current_loop") if state else None,
            "max_loops": state.get("max_loops") if state else None,
            "stop_reason": state.get("stop_reason") if state else None,
            "loop_count": len(state.get("loops", [])) if state else 0,
            "manual_review_count": len(state.get("manual_review", [])) if state else 0,
            "resolved_findings_count": len(state.get("resolved_findings", [])) if state else 0,
            "deterministic_checks_count": len(state.get("deterministic_checks", [])) if state else 0,
        },
        "inventory": {
            "present": inventory is not None,
            "error": inventory_error,
            "base_resolved": inventory.get("base_resolved") if inventory else None,
            "merge_base": inventory.get("merge_base") if inventory else None,
            "file_count": inventory.get("file_count") if inventory else None,
            "untracked_file_count": len(inventory.get("untracked_files_included", [])) if inventory else 0,
            "risk_tags": inventory.get("risk_tags") if inventory else [],
            "full_diff_path": inventory.get("full_diff_path") if inventory else None,
        },
        "slices": {
            "preliminary_present": preliminary is not None,
            "preliminary_error": preliminary_error,
            "preliminary_count": len(preliminary.get("slices", [])) if preliminary else 0,
            "semantic_present": semantic is not None,
            "semantic_error": semantic_error,
            "semantic_count": len(semantic.get("slices", [])) if semantic else 0,
            "semantic_ids": [s.get("id") for s in (semantic.get("slices", []) if semantic else [])[:30]],
        },
        "findings": {
            "raw_json_count": len(raw_files),
            "verified_json_count": len(verified_files),
            "dedupe_candidates_present": dedupe_candidates is not None,
            "dedupe_candidates_error": dedupe_candidates_error,
            "candidate_input_finding_count": dedupe_candidates.get("input_finding_count") if dedupe_candidates else None,
            "candidate_qualifying_finding_count": (
                dedupe_candidates.get("qualifying_finding_count") if dedupe_candidates else None
            ),
            "dedupe_skipped": dedupe_candidates.get("skipped") if dedupe_candidates else None,
            "dedupe_skip_reason": dedupe_candidates.get("skip_reason") if dedupe_candidates else None,
            "candidate_pair_count": dedupe_candidates.get("candidate_pair_count") if dedupe_candidates else None,
            "deduped_present": deduped is not None,
            "deduped_error": deduped_error,
            "canonical_count": bucket_count(deduped, "blocking") + bucket_count(deduped, "important"),
        },
        "manual_review_markdown_item_count": count_markdown_items(review_dir / "manual-review.md"),
    }


def print_markdown(status: Dict[str, Any]) -> None:
    print(f"# Review status: {status['session']['review_dir']}")
    print()
    print("## Session")
    print(json.dumps(status["session"], indent=2))
    print()
    print("## State")
    print(json.dumps(status["state"], indent=2))
    print()
    print("## Inventory")
    print(json.dumps(status["inventory"], indent=2))
    print()
    print("## Slices")
    print(json.dumps(status["slices"], indent=2))
    print()
    print("## Findings")
    print(json.dumps(status["findings"], indent=2))
    print()
    print(f"manual_review_markdown_item_count: {status['manual_review_markdown_item_count']}")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize review-stack session state")
    ap.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of markdown")
    args = ap.parse_args(argv)
    if not args.review_dir:
        ap.error("--review-dir is required unless REVIEW_DIR is set")
    status = collect_status(Path(args.review_dir))
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print_markdown(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
