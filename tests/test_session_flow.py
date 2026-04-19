from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import init_repo, python_script, read_json, run


class SessionFlowTests(unittest.TestCase):
    def test_inventory_allocates_distinct_named_sessions_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)
            first = json.loads(run(python_script("review-inventory.py") + ["--base", "HEAD"], root).stdout)
            second = json.loads(run(python_script("review-inventory.py") + ["--base", "HEAD"], root).stdout)
            self.assertNotEqual(first["review_dir"], second["review_dir"])
            self.assertNotEqual(first["session_id"], second["session_id"])
            self.assertTrue((root / first["review_dir"] / "inventory.json").exists())
            self.assertTrue((root / second["review_dir"] / "inventory.json").exists())

    def test_inventory_reuses_existing_session_metadata_when_review_dir_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)
            first = json.loads(run(python_script("review-inventory.py") + ["--base", "HEAD"], root).stdout)
            review_dir = first["review_dir"]
            state_before = read_json(root / review_dir / "state.json")
            second = json.loads(
                run(python_script("review-inventory.py") + ["--base", "HEAD", "--review-dir", review_dir], root).stdout
            )
            state_after = read_json(root / review_dir / "state.json")
            self.assertEqual(second["review_dir"], review_dir)
            self.assertEqual(second["session_id"], first["session_id"])
            self.assertEqual(state_before["session_id"], state_after["session_id"])
            self.assertEqual(state_before["started_at"], state_after["started_at"])
