from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import python_script, run


class StatusTests(unittest.TestCase):
    def test_status_reports_counts_and_session_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            review = root / ".review-sessions" / "test-audit-abc123"
            (review / "raw-findings" / "loop-1").mkdir(parents=True)
            (review / "verified" / "loop-1").mkdir(parents=True)
            (review / "state.json").write_text(
                json.dumps(
                    {
                        "session_id": "test-audit-abc123",
                        "review_dir": ".review-sessions/test-audit-abc123",
                        "repo_root": str(root),
                        "head_sha": "deadbeef",
                        "base": "HEAD",
                        "merge_base": "abc",
                        "mode": "audit",
                        "current_loop": 1,
                        "max_loops": 6,
                        "loops": [{}],
                        "manual_review": [],
                        "resolved_findings": [],
                        "deterministic_checks": [],
                    }
                ),
                encoding="utf-8",
            )
            (review / "inventory.json").write_text(
                json.dumps(
                    {
                        "session_id": "test-audit-abc123",
                        "review_dir": ".review-sessions/test-audit-abc123",
                        "repo_root": str(root),
                        "head_sha": "deadbeef",
                        "base_resolved": "HEAD",
                        "merge_base": "abc",
                        "file_count": 1,
                        "untracked_files_included": [],
                        "risk_tags": ["general"],
                        "full_diff_path": ".review-sessions/test-audit-abc123/full.diff",
                    }
                ),
                encoding="utf-8",
            )
            (review / "slices.preliminary.json").write_text(json.dumps({"slices": [{}]}), encoding="utf-8")
            (review / "semantic-slices.json").write_text(json.dumps({"slices": [{"id": "one"}]}), encoding="utf-8")
            (review / "dedupe-candidates.json").write_text(
                json.dumps(
                    {
                        "algorithm": "dedupe-candidate-index-v2",
                        "note": "candidate hints only",
                        "skipped": False,
                        "skip_reason": "",
                        "input_finding_count": 2,
                        "qualifying_finding_count": 2,
                        "skipped_low_signal_count": 0,
                        "qualifying_severities": ["blocking", "important"],
                        "candidate_pair_count": 1,
                        "finding_refs": [],
                        "candidate_pairs": [],
                    }
                ),
                encoding="utf-8",
            )
            (review / "deduped-findings.json").write_text(
                json.dumps({"blocking": [{}], "important": [], "question": [], "nit": [], "pre_existing": []}),
                encoding="utf-8",
            )
            (review / "raw-findings" / "loop-1" / "a.json").write_text("{}", encoding="utf-8")
            (review / "verified" / "loop-1" / "a.json").write_text("{}", encoding="utf-8")
            proc = run(
                python_script("review-status.py") + ["--review-dir", ".review-sessions/test-audit-abc123", "--json"],
                root,
            )
            status = json.loads(proc.stdout)
            self.assertEqual(status["session"]["session_id"], "test-audit-abc123")
            self.assertEqual(status["slices"]["semantic_count"], 1)
            self.assertEqual(status["findings"]["candidate_qualifying_finding_count"], 2)
            self.assertEqual(status["findings"]["candidate_pair_count"], 1)
            self.assertEqual(status["findings"]["canonical_count"], 1)
