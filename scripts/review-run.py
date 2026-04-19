#!/usr/bin/env python3
"""Thin orchestration wrapper for review-stack session bootstrap and state updates."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent


def forward(script_name: str, args: Sequence[str]) -> int:
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def add_review_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Orchestrate review-stack inventory, state, and status helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="Build or refresh session inventory and state")
    p.add_argument("--base", default=os.environ.get("REVIEW_BASE", "origin/main"))
    p.add_argument("--mode", choices=["audit", "fix"], default=os.environ.get("REVIEW_MODE", "audit"))
    p.add_argument("--max-loops", type=int, default=int(os.environ.get("REVIEW_MAX_LOOPS", "6")))
    p.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))
    p.add_argument(
        "--exclude-prefix",
        action="append",
        default=[],
        help="Additional repo-relative path prefix to exclude. May be repeated or comma-separated.",
    )

    p = sub.add_parser("status", help="Summarize the current session")
    add_review_dir_arg(p)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("start-loop", help="Start a review loop")
    add_review_dir_arg(p)
    p.add_argument("--note", default="")

    p = sub.add_parser("record-check", help="Record one deterministic validation check")
    add_review_dir_arg(p)
    p.add_argument("--command", required=True)
    p.add_argument("--status", choices=["pass", "fail", "skipped", "unknown"], required=True)
    p.add_argument("--note", default="")

    p = sub.add_parser("finish-loop", help="Finish the current review loop")
    add_review_dir_arg(p)
    p.add_argument("--new-confirmed", type=int, default=0)
    p.add_argument("--remaining-confirmed", type=int, default=0)
    p.add_argument("--fixes-applied", type=int, default=0)
    p.add_argument("--deterministic-gates-passing", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--note", default="")

    p = sub.add_parser("stop", help="Record the terminal stop reason")
    add_review_dir_arg(p)
    p.add_argument("reason")

    args = ap.parse_args(argv)

    if args.cmd == "prepare":
        child_args = [
            "--base",
            args.base,
            "--mode",
            args.mode,
            "--max-loops",
            str(args.max_loops),
        ]
        if args.review_dir:
            child_args.extend(["--review-dir", args.review_dir])
        for prefix in args.exclude_prefix:
            child_args.extend(["--exclude-prefix", prefix])
        return forward("review-inventory.py", child_args)

    if args.cmd == "status":
        child_args = []
        if args.review_dir:
            child_args.extend(["--review-dir", args.review_dir])
        if args.json:
            child_args.append("--json")
        return forward("review-status.py", child_args)

    if args.cmd == "start-loop":
        if not args.review_dir:
            ap.error("--review-dir is required unless REVIEW_DIR is set")
        return forward("review-state.py", ["--review-dir", args.review_dir, "start-loop", "--note", args.note])

    if args.cmd == "record-check":
        if not args.review_dir:
            ap.error("--review-dir is required unless REVIEW_DIR is set")
        return forward(
            "review-state.py",
            [
                "--review-dir",
                args.review_dir,
                "record-check",
                "--command",
                args.command,
                "--status",
                args.status,
                "--note",
                args.note,
            ],
        )

    if args.cmd == "finish-loop":
        if not args.review_dir:
            ap.error("--review-dir is required unless REVIEW_DIR is set")
        return forward(
            "review-state.py",
            [
                "--review-dir",
                args.review_dir,
                "finish-loop",
                "--new-confirmed",
                str(args.new_confirmed),
                "--remaining-confirmed",
                str(args.remaining_confirmed),
                "--fixes-applied",
                str(args.fixes_applied),
                "--deterministic-gates-passing",
                args.deterministic_gates_passing,
                "--note",
                args.note,
            ],
        )

    if args.cmd == "stop":
        if not args.review_dir:
            ap.error("--review-dir is required unless REVIEW_DIR is set")
        return forward("review-state.py", ["--review-dir", args.review_dir, "stop", args.reason])

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
