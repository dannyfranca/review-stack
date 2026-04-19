#!/usr/bin/env python3
"""Maintain review-stack loop state.

Purpose
-------
This is the durable loop ledger. It is useful because the parent agent can be
restarted, interrupted, or re-run while `<review-dir>/state.json` preserves loop
number, convergence counters, deterministic check summaries, stop reason, and
manual-review/resolution references.

The script writes only the selected review directory state file.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state(
    *,
    session_id: str = "",
    review_dir: str = "",
    repo_root: str = "",
    head_sha: str = "",
    base: str = "origin/main",
    merge_base: str = "",
    mode: str = "audit",
    max_loops: int = 6,
) -> Dict[str, Any]:
    now = now_iso()
    return {
        "version": 1,
        "session_id": session_id,
        "review_dir": review_dir,
        "repo_root": repo_root,
        "head_sha": head_sha,
        "base": base,
        "merge_base": merge_base,
        "mode": mode,
        "current_loop": 0,
        "max_loops": max_loops,
        "started_at": now,
        "last_updated_at": now,
        "loops": [],
        "canonical_findings": [],
        "resolved_findings": [],
        "manual_review": [],
        "deterministic_checks": [],
        "stop_reason": "",
    }


def state_path(review_dir: Path) -> Path:
    return review_dir / "state.json"


def load_state(review_dir: Path, *, base: str = "origin/main", mode: str = "audit", max_loops: int = 6) -> Dict[str, Any]:
    path = state_path(review_dir)
    if not path.exists():
        return default_state(base=base, mode=mode, max_loops=max_loops)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = default_state(base=base, mode=mode, max_loops=max_loops)
    data.setdefault("version", 1)
    data.setdefault("session_id", "")
    data.setdefault("review_dir", str(review_dir))
    data.setdefault("repo_root", "")
    data.setdefault("head_sha", "")
    data.setdefault("base", base)
    data.setdefault("merge_base", "")
    data.setdefault("mode", mode)
    data.setdefault("current_loop", 0)
    data.setdefault("max_loops", max_loops)
    data.setdefault("loops", [])
    data.setdefault("canonical_findings", [])
    data.setdefault("resolved_findings", [])
    data.setdefault("manual_review", [])
    data.setdefault("deterministic_checks", [])
    data.setdefault("stop_reason", "")
    return data


def save_state(review_dir: Path, state: Dict[str, Any]) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    state.setdefault("review_dir", str(review_dir))
    state["last_updated_at"] = now_iso()
    state_path(review_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")


def current_loop_record(state: Dict[str, Any]) -> Dict[str, Any]:
    loops = state.setdefault("loops", [])
    if not loops:
        loops.append({"loop": int(state.get("current_loop", 0)) or 1})
    return loops[-1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Maintain review-stack session state")
    ap.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--session-id", default="")
    p.add_argument("--review-dir-label", default="")
    p.add_argument("--repo-root", default="")
    p.add_argument("--head-sha", default="")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--mode", choices=["audit", "fix"], default="audit")
    p.add_argument("--max-loops", type=int, default=6)
    p.add_argument("--merge-base", default="")

    sub.add_parser("show")

    p = sub.add_parser("start-loop")
    p.add_argument("--note", default="")

    p = sub.add_parser("finish-loop")
    p.add_argument("--new-confirmed", type=int, default=0)
    p.add_argument("--remaining-confirmed", type=int, default=0)
    p.add_argument("--fixes-applied", type=int, default=0)
    p.add_argument("--deterministic-gates-passing", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--note", default="")

    p = sub.add_parser("record-check")
    p.add_argument("--command", required=True)
    p.add_argument("--status", choices=["pass", "fail", "skipped", "unknown"], required=True)
    p.add_argument("--note", default="")

    p = sub.add_parser("stop")
    p.add_argument("reason")

    args = ap.parse_args(argv)
    if not args.review_dir:
        ap.error("--review-dir is required unless REVIEW_DIR is set")
    review_dir = Path(args.review_dir)

    if args.cmd == "init":
        state = default_state(
            session_id=args.session_id,
            review_dir=args.review_dir_label or str(review_dir),
            repo_root=args.repo_root,
            head_sha=args.head_sha,
            base=args.base,
            merge_base=args.merge_base,
            mode=args.mode,
            max_loops=args.max_loops,
        )
        save_state(review_dir, state)
        print(json.dumps({"state": str(state_path(review_dir)), "current_loop": state["current_loop"]}, indent=2))
        return 0

    state = load_state(review_dir)

    if args.cmd == "show":
        print(json.dumps(state, indent=2))
        return 0

    if args.cmd == "start-loop":
        state["current_loop"] = int(state.get("current_loop", 0)) + 1
        state.setdefault("loops", []).append(
            {
                "loop": state["current_loop"],
                "started_at": now_iso(),
                "note": args.note,
                "new_confirmed": None,
                "remaining_confirmed": None,
                "fixes_applied": None,
                "deterministic_gates_passing": "unknown",
            }
        )
        save_state(review_dir, state)
        print(json.dumps({"current_loop": state["current_loop"]}, indent=2))
        return 0

    if args.cmd == "finish-loop":
        loop = current_loop_record(state)
        loop.update(
            {
                "finished_at": now_iso(),
                "new_confirmed": args.new_confirmed,
                "remaining_confirmed": args.remaining_confirmed,
                "fixes_applied": args.fixes_applied,
                "deterministic_gates_passing": args.deterministic_gates_passing,
                "note": args.note,
            }
        )
        save_state(review_dir, state)
        print(json.dumps(loop, indent=2))
        return 0

    if args.cmd == "record-check":
        state.setdefault("deterministic_checks", []).append(
            {"command": args.command, "status": args.status, "note": args.note, "recorded_at": now_iso()}
        )
        save_state(review_dir, state)
        print(json.dumps({"recorded": args.command, "status": args.status}, indent=2))
        return 0

    if args.cmd == "stop":
        state["stop_reason"] = args.reason
        save_state(review_dir, state)
        print(json.dumps({"stop_reason": args.reason}, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
