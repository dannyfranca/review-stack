from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import init_repo, python_script, run


class ReviewRunTests(unittest.TestCase):
    def test_prepare_and_loop_bookkeeping_work_through_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)

            prepare = json.loads(run(python_script("review-run.py") + ["prepare", "--base", "HEAD"], root).stdout)
            review_dir = prepare["review_dir"]
            self.assertTrue(review_dir.startswith(".review-sessions/"))

            run(python_script("review-run.py") + ["start-loop", "--review-dir", review_dir, "--note", "first pass"], root)
            run(
                python_script("review-run.py")
                + [
                    "record-check",
                    "--review-dir",
                    review_dir,
                    "--command",
                    "python3 -m unittest",
                    "--status",
                    "pass",
                    "--note",
                    "smoke",
                ],
                root,
            )
            run(
                python_script("review-run.py")
                + [
                    "finish-loop",
                    "--review-dir",
                    review_dir,
                    "--new-confirmed",
                    "0",
                    "--remaining-confirmed",
                    "0",
                    "--fixes-applied",
                    "0",
                    "--deterministic-gates-passing",
                    "true",
                ],
                root,
            )
            run(python_script("review-run.py") + ["stop", "--review-dir", review_dir, "ready"], root)

            status = json.loads(
                run(python_script("review-run.py") + ["status", "--review-dir", review_dir, "--json"], root).stdout
            )
            self.assertEqual(status["state"]["current_loop"], 1)
            self.assertEqual(status["state"]["stop_reason"], "ready")
            self.assertEqual(status["state"]["deterministic_checks_count"], 1)

    def test_prepare_reuses_existing_review_dir_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)

            first = json.loads(run(python_script("review-run.py") + ["prepare", "--base", "HEAD"], root).stdout)
            second = json.loads(
                run(
                    python_script("review-run.py")
                    + ["prepare", "--base", "HEAD", "--review-dir", first["review_dir"]],
                    root,
                ).stdout
            )

            self.assertEqual(second["review_dir"], first["review_dir"])
            self.assertEqual(second["session_id"], first["session_id"])
            self.assertFalse(second["review_dir_allocated"])


if __name__ == "__main__":
    unittest.main()
