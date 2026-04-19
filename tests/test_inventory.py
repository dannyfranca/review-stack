from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import init_repo, python_script, read_json, run


class InventoryTests(unittest.TestCase):
    def test_inventory_excludes_review_state_and_includes_untracked_text_content(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)
            review_dir = ".review-sessions/test-audit-abc123"
            (root / "app.py").write_text("def existing():\n    return 2\n", encoding="utf-8")
            (root / "new_endpoint.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
            (root / ".review").mkdir()
            (root / ".review" / "old-state.json").write_text('{"stale": true}\n', encoding="utf-8")
            (root / ".review-sessions" / "older").mkdir(parents=True)
            (root / ".review-sessions" / "older" / "state.json").write_text('{"stale": true}\n', encoding="utf-8")

            proc = run(python_script("review-inventory.py") + ["--base", "HEAD", "--review-dir", review_dir], root)
            self.assertIn("untracked_file_count", proc.stdout)

            inventory = read_json(root / review_dir / "inventory.json")
            paths = {f["path"] for f in inventory["files"]}
            self.assertIn("app.py", paths)
            self.assertIn("new_endpoint.py", paths)
            self.assertNotIn(".review/old-state.json", paths)
            self.assertNotIn(".review-sessions/older/state.json", paths)

            full_diff = (root / review_dir / "full.diff").read_text(encoding="utf-8")
            self.assertIn("diff --git a/new_endpoint.py b/new_endpoint.py", full_diff)
            self.assertIn("+def handler():", full_diff)
            self.assertNotIn("old-state.json", full_diff)

    def test_inventory_default_allocates_named_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_repo(root)
            proc = run(python_script("review-inventory.py") + ["--base", "HEAD"], root)
            data = json.loads(proc.stdout)
            self.assertTrue(data["review_dir"].startswith(".review-sessions/"))
            self.assertTrue(data["review_dir_allocated"])
            self.assertTrue(data["session_id"])
            self.assertTrue((root / data["review_dir"] / "inventory.json").exists())
            inventory = read_json(root / data["review_dir"] / "inventory.json")
            self.assertEqual(inventory["session_id"], data["session_id"])
            self.assertEqual(inventory["review_dir"], data["review_dir"])
