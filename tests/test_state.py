from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import python_script, read_json, run


class StateTests(unittest.TestCase):
    def test_state_helper_records_loop_checks_and_session_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            review_dir = ".review-sessions/test-audit-123abc"
            run(
                python_script("review-state.py")
                + [
                    "--review-dir",
                    review_dir,
                    "init",
                    "--session-id",
                    "test-audit-123abc",
                    "--review-dir-label",
                    review_dir,
                    "--repo-root",
                    str(root),
                    "--head-sha",
                    "deadbeef",
                    "--base",
                    "HEAD",
                    "--merge-base",
                    "abc123",
                    "--mode",
                    "audit",
                    "--max-loops",
                    "3",
                ],
                root,
            )
            run(python_script("review-state.py") + ["--review-dir", review_dir, "start-loop", "--note", "first pass"], root)
            run(
                python_script("review-state.py")
                + ["--review-dir", review_dir, "record-check", "--command", "pytest", "--status", "pass"],
                root,
            )
            run(
                python_script("review-state.py")
                + [
                    "--review-dir",
                    review_dir,
                    "finish-loop",
                    "--new-confirmed",
                    "0",
                    "--remaining-confirmed",
                    "0",
                    "--deterministic-gates-passing",
                    "true",
                ],
                root,
            )
            run(python_script("review-state.py") + ["--review-dir", review_dir, "stop", "ready"], root)
            state = read_json(root / review_dir / "state.json")
            self.assertEqual(state["session_id"], "test-audit-123abc")
            self.assertEqual(state["review_dir"], review_dir)
            self.assertEqual(state["head_sha"], "deadbeef")
            self.assertEqual(state["merge_base"], "abc123")
            self.assertEqual(state["current_loop"], 1)
            self.assertEqual(state["stop_reason"], "ready")
            self.assertEqual(state["deterministic_checks"][0]["command"], "pytest")
            self.assertEqual(state["loops"][0]["deterministic_gates_passing"], "true")
