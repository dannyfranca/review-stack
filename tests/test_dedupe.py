from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import python_script, read_json, run


class DedupeCandidateTests(unittest.TestCase):
    def write_raw(self, root: Path, findings: list[dict]) -> None:
        raw = root / ".review-sessions" / "test-audit-abc123" / "raw-findings" / "loop-1"
        raw.mkdir(parents=True)
        (raw / "reviewer.json").write_text(
            __import__("json").dumps(
                {"agent": "review_diff_bug", "loop": 1, "scope": "whole_diff", "summary": "", "findings": findings}
            ),
            encoding="utf-8",
        )

    def test_small_sessions_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_raw(
                root,
                [
                    {
                        "id": "a",
                        "title": "GET /invoice misses auth",
                        "severity": "important",
                        "category": "security",
                        "file": "src/api/invoices.ts",
                        "line_start": 10,
                        "line_end": 12,
                        "claim": "GET /invoice can be called without auth.",
                        "evidence": "GET handler has no requireUser call.",
                        "suggested_fix": "Call requireUser before reading."
                    },
                    {
                        "id": "b",
                        "title": "POST /invoice returns wrong status",
                        "severity": "important",
                        "category": "api_contract",
                        "file": "src/api/invoices.ts",
                        "line_start": 90,
                        "line_end": 95,
                        "claim": "POST /invoice returns 200 instead of 201.",
                        "evidence": "POST handler returns ok response after create.",
                        "suggested_fix": "Return created status."
                    },
                ],
            )
            run(
                python_script("review-dedupe.py") + ["--review-dir", ".review-sessions/test-audit-abc123"],
                root,
            )
            out = read_json(root / ".review-sessions" / "test-audit-abc123" / "dedupe-candidates.json")
            self.assertEqual(out["input_finding_count"], 2)
            self.assertEqual(out["qualifying_finding_count"], 2)
            self.assertTrue(out["skipped"])
            self.assertEqual(out["candidate_pair_count"], 0)
            self.assertEqual(len(out["finding_refs"]), 2)

    def test_distinct_bugs_in_same_file_are_not_candidate_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_raw(
                root,
                [
                    {
                        "id": "a",
                        "title": "GET /invoice misses auth",
                        "severity": "important",
                        "category": "security",
                        "file": "src/api/invoices.ts",
                        "line_start": 10,
                        "line_end": 12,
                        "claim": "GET /invoice can be called without auth.",
                        "evidence": "GET handler has no requireUser call.",
                        "suggested_fix": "Call requireUser before reading."
                    },
                    {
                        "id": "b",
                        "title": "POST /invoice returns wrong status",
                        "severity": "important",
                        "category": "api_contract",
                        "file": "src/api/invoices.ts",
                        "line_start": 90,
                        "line_end": 95,
                        "claim": "POST /invoice returns 200 instead of 201.",
                        "evidence": "POST handler returns ok response after create.",
                        "suggested_fix": "Return created status."
                    },
                ],
            )
            run(
                python_script("review-dedupe.py")
                + ["--review-dir", ".review-sessions/test-audit-abc123", "--min-findings", "2"],
                root,
            )
            out = read_json(root / ".review-sessions" / "test-audit-abc123" / "dedupe-candidates.json")
            self.assertFalse(out["skipped"])
            self.assertEqual(out["candidate_pair_count"], 0)
            self.assertEqual(len(out["finding_refs"]), 2)

    def test_likely_duplicate_pair_is_preserved_as_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_raw(
                root,
                [
                    {
                        "id": "a",
                        "title": "Invoice lookup is not tenant scoped",
                        "severity": "blocking",
                        "category": "security",
                        "file": "src/api/invoices.ts",
                        "line_start": 40,
                        "line_end": 45,
                        "claim": "`GET /invoices/:id` calls `getInvoice(id)` without tenant scoping.",
                        "evidence": "Handler passes only invoice id.",
                        "suggested_fix": "Use getInvoiceForTenant(id, tenantId)."
                    },
                    {
                        "id": "b",
                        "title": "Tenant isolation missing for invoice read",
                        "severity": "important",
                        "category": "security",
                        "file": "src/api/invoices.ts",
                        "line_start": 43,
                        "line_end": 47,
                        "claim": "`GET /invoices/:id` uses `getInvoice(id)`, so another tenant invoice can be read.",
                        "evidence": "No tenantId appears in the DB lookup.",
                        "suggested_fix": "Use getInvoiceForTenant(id, tenantId)."
                    },
                ],
            )
            run(
                python_script("review-dedupe.py")
                + ["--review-dir", ".review-sessions/test-audit-abc123", "--min-findings", "2"],
                root,
            )
            out = read_json(root / ".review-sessions" / "test-audit-abc123" / "dedupe-candidates.json")
            self.assertEqual(out["input_finding_count"], 2)
            self.assertEqual(out["qualifying_finding_count"], 2)
            self.assertFalse(out["skipped"])
            self.assertEqual(out["candidate_pair_count"], 1)
            self.assertEqual(len(out["finding_refs"]), 2)
            self.assertIn("Candidate only", out["candidate_pairs"][0]["note"])
