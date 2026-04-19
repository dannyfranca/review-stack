#!/usr/bin/env python3
"""Build non-authoritative duplicate-candidate hints for review-stack.

Purpose
-------
Dedupe is a contextual review decision. This script does **not** decide the
canonical issue queue and does **not** remove findings. It is only an optional
accelerator for noisy review waves: it indexes higher-signal raw findings and
proposes possible duplicate pairs with transparent signals so the
`review_aggregator` agent can perform contextual dedupe using the code, diff,
semantic slices, and verifier results.

Safety properties
-----------------
- every raw finding remains in its original reviewer JSON;
- output is written to `<review-dir>/dedupe-candidates.json` by default;
- no finding is marked duplicate by this script;
- pair hints are optional and non-authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from review_common import resolve_review_dir

DEFAULT_QUALIFYING_SEVERITIES = ("blocking", "important")
DEFAULT_MIN_FINDINGS = 4


def norm_text(value: Any) -> str:
    """Normalize text for rough matching without pretending it is semantic."""
    s = str(value or "").lower()
    s = re.sub(r"https?://\S+", " url ", s)
    s = re.sub(r"[^a-z0-9_./: -]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def text_blob(finding: Dict[str, Any]) -> str:
    """Return the fields that best describe the claimed root cause."""
    return norm_text(
        " ".join(
            str(finding.get(k, ""))
            for k in ("title", "claim", "evidence", "suggested_fix", "verification_needed")
        )
    )


def line_range(finding: Dict[str, Any]) -> Tuple[int | None, int | None]:
    """Return normalized `(start, end)` line range if present."""

    def to_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    start = to_int(finding.get("line_start"))
    end = to_int(finding.get("line_end"))
    if start is not None and end is None:
        end = start
    if start is not None and end is not None and end < start:
        start, end = end, start
    return start, end


def ranges_overlap_or_near(a: Dict[str, Any], b: Dict[str, Any], *, tolerance: int = 8) -> bool:
    """Return whether two findings point to nearby changed lines."""
    a_start, a_end = line_range(a)
    b_start, b_end = line_range(b)
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return False
    return not (a_end + tolerance < b_start or b_end + tolerance < a_start)


def extract_symbols(finding: Dict[str, Any]) -> set[str]:
    """Extract route/function/scope hints for pair suggestions.

    This is intentionally a weak signal. It is useful for finding likely pairs,
    not for deciding canonical duplicates.
    """
    values: List[str] = []
    for key in (
        "symbol",
        "symbols",
        "affected_symbol",
        "affected_symbols",
        "entrypoint",
        "entrypoints",
        "route",
        "routes",
        "api",
        "apis",
        "slice_id",
        "scope",
    ):
        raw = finding.get(key)
        if isinstance(raw, list):
            values.extend(str(x) for x in raw)
        elif raw:
            values.append(str(raw))

    haystack = " ".join(
        str(finding.get(k, "")) for k in ("title", "claim", "evidence", "suggested_fix", "verification_needed")
    )
    values.extend(re.findall(r"`([^`]{2,120})`", haystack))
    values.extend(re.findall(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+[/A-Za-z0-9_{}:.-]+", haystack))
    values.extend(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\s*\(", haystack))
    return {norm_text(v).rstrip("(") for v in values if norm_text(v)}


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def stable_uid(finding: Dict[str, Any], fallback_index: int) -> str:
    """Return a stable identifier for one raw finding within this review run."""
    parts = [
        str(finding.get("_source_file", "")),
        str(finding.get("_source_agent", "")),
        str(finding.get("id", "")),
        str(finding.get("file", "")),
        str(finding.get("line_start", "")),
        str(finding.get("title", "")),
        str(fallback_index),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def finding_ref(finding: Dict[str, Any]) -> Dict[str, Any]:
    """Return a lightweight pointer back to the original raw finding."""
    return {
        "uid": finding["_uid"],
        "id": finding.get("id", ""),
        "severity": finding.get("severity", ""),
        "category": finding.get("category", ""),
        "title": finding.get("title", ""),
        "file": finding.get("file", ""),
        "line_start": finding.get("line_start"),
        "line_end": finding.get("line_end"),
        "source_file": finding.get("_source_file", ""),
        "source_agent": finding.get("_source_agent", ""),
        "source_index": finding.get("_source_index"),
    }


def pair_signals(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Compute transparent duplicate-candidate signals for a pair."""
    reasons: List[str] = []
    score = 0

    same_category = bool(norm_text(a.get("category"))) and norm_text(a.get("category")) == norm_text(b.get("category"))
    same_file = bool(norm_text(a.get("file"))) and norm_text(a.get("file")) == norm_text(b.get("file"))
    nearby_lines = ranges_overlap_or_near(a, b)
    symbols_a = extract_symbols(a)
    symbols_b = extract_symbols(b)
    shared_symbols = sorted(symbols_a & symbols_b)
    text_similarity = similarity(text_blob(a), text_blob(b))
    same_fix_direction = similarity(norm_text(a.get("suggested_fix")), norm_text(b.get("suggested_fix"))) >= 0.70

    if same_category:
        score += 1
        reasons.append("same category")
    if same_file:
        score += 1
        reasons.append("same file")
    if nearby_lines:
        score += 3
        reasons.append("near/overlapping line range")
    if shared_symbols:
        score += 3
        reasons.append("shared symbol/entrypoint: " + ", ".join(shared_symbols[:5]))
    if text_similarity >= 0.82:
        score += 3
        reasons.append(f"very similar claim text {text_similarity:.2f}")
    elif text_similarity >= 0.68:
        score += 2
        reasons.append(f"similar claim text {text_similarity:.2f}")
    elif text_similarity >= 0.55:
        score += 1
        reasons.append(f"weakly similar claim text {text_similarity:.2f}")
    if same_fix_direction:
        score += 1
        reasons.append("similar fix direction")

    return {
        "score": score,
        "reasons": reasons,
        "same_category": same_category,
        "same_file": same_file,
        "nearby_lines": nearby_lines,
        "shared_symbols": shared_symbols,
        "text_similarity": round(text_similarity, 3),
        "same_fix_direction": same_fix_direction,
    }


def likely_candidate_pair(a: Dict[str, Any], b: Dict[str, Any], signals: Dict[str, Any]) -> bool:
    """Return True when a pair is worth showing to the contextual aggregator.

    Thresholds are conservative. Same file alone never qualifies; distinct bugs
    in one handler should remain separate unless there is a stronger relation.
    """
    if signals["nearby_lines"] and (signals["same_file"] or signals["shared_symbols"]):
        return True
    if signals["shared_symbols"] and signals["text_similarity"] >= 0.55:
        return True
    if signals["same_category"] and signals["text_similarity"] >= 0.82:
        return True
    if signals["same_file"] and signals["text_similarity"] >= 0.75 and signals["same_fix_direction"]:
        return True
    return False


def iter_findings(raw_dir: Path) -> Iterable[Dict[str, Any]]:
    """Yield raw findings from reviewer JSON files under `raw_dir`."""
    for path in sorted(raw_dir.glob("**/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        findings = data.get("findings") if isinstance(data, dict) else None
        if not isinstance(findings, list):
            continue
        for idx, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            f = dict(finding)
            f["_source_file"] = str(path)
            f["_source_agent"] = data.get("agent", path.stem)
            f["_source_index"] = idx
            yield f


def parse_severities(values: Sequence[str] | None) -> List[str]:
    if not values:
        return list(DEFAULT_QUALIFYING_SEVERITIES)
    parsed: List[str] = []
    for value in values:
        parsed.extend(norm_text(part) for part in value.split(","))
    return [value for value in parsed if value]


def build_candidate_index(
    findings: Sequence[Dict[str, Any]],
    *,
    qualifying_severities: Sequence[str],
    min_findings: int,
) -> Dict[str, Any]:
    """Return lightweight duplicate-pair hints for high-signal findings only."""
    enriched: List[Dict[str, Any]] = []
    for idx, finding in enumerate(findings):
        severity = norm_text(finding.get("severity"))
        if severity not in qualifying_severities:
            continue
        f = dict(finding)
        f["_uid"] = stable_uid(f, idx)
        f["_symbols"] = sorted(extract_symbols(f))[:20]
        enriched.append(f)

    note = (
        "This file is not the canonical queue. It keeps only lightweight references to higher-signal "
        "raw findings and suggests possible duplicate pairs for contextual review_aggregator dedupe."
    )
    if len(enriched) < min_findings:
        return {
            "algorithm": "dedupe-candidate-index-v2",
            "note": note,
            "skipped": True,
            "skip_reason": f"qualifying findings {len(enriched)} below min_findings {min_findings}",
            "input_finding_count": len(findings),
            "qualifying_finding_count": len(enriched),
            "skipped_low_signal_count": len(findings) - len(enriched),
            "qualifying_severities": list(qualifying_severities),
            "candidate_pair_count": 0,
            "finding_refs": [finding_ref(f) for f in enriched],
            "candidate_pairs": [],
        }

    candidate_pairs: List[Dict[str, Any]] = []
    pair_indexes: set[Tuple[int, int]] = set()
    buckets: Dict[Tuple[str, str], set[int]] = {}

    def bucket_add(key: Tuple[str, str], value: int) -> None:
        bucket = buckets.setdefault(key, set())
        bucket.add(value)

    for idx, finding in enumerate(enriched):
        file_name = norm_text(finding.get("file"))
        category = norm_text(finding.get("category"))
        if file_name:
            bucket_add(("file", file_name), idx)
        if category:
            bucket_add(("category", category), idx)
        for symbol in finding.get("_symbols", [])[:8]:
            if symbol:
                bucket_add(("symbol", symbol), idx)

    for indexes in buckets.values():
        ordered = sorted(indexes)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pair_indexes.add((a, b))

    if not pair_indexes:
        pair_indexes = {(i, j) for i in range(len(enriched)) for j in range(i + 1, len(enriched))}

    for i, j in sorted(pair_indexes):
        signals = pair_signals(enriched[i], enriched[j])
        if likely_candidate_pair(enriched[i], enriched[j], signals):
            candidate_pairs.append(
                {
                    "a": enriched[i]["_uid"],
                    "b": enriched[j]["_uid"],
                    "score": signals["score"],
                    "reasons": signals["reasons"],
                    "signals": signals,
                    "note": "Candidate only. Aggregator must confirm, split, or ignore contextually.",
                }
            )

    return {
        "algorithm": "dedupe-candidate-index-v2",
        "note": note,
        "skipped": False,
        "skip_reason": "",
        "input_finding_count": len(findings),
        "qualifying_finding_count": len(enriched),
        "skipped_low_signal_count": len(findings) - len(enriched),
        "qualifying_severities": list(qualifying_severities),
        "candidate_pair_count": len(candidate_pairs),
        "finding_refs": [finding_ref(f) for f in enriched],
        "candidate_pairs": sorted(candidate_pairs, key=lambda p: (-p["score"], p["a"], p["b"])),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build non-authoritative duplicate-candidate hints for review-stack findings")
    ap.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))
    ap.add_argument("--raw-dir")
    ap.add_argument("--out")
    ap.add_argument(
        "--severity",
        action="append",
        help="Qualifying severities to consider. May be repeated or comma-separated. Defaults to blocking,important.",
    )
    ap.add_argument(
        "--min-findings",
        type=int,
        default=int(os.environ.get("REVIEW_DEDUPE_MIN_FINDINGS", str(DEFAULT_MIN_FINDINGS))),
        help="Skip pair generation when fewer than this many qualifying findings are present.",
    )
    args = ap.parse_args(argv)

    if not args.review_dir:
        ap.error("--review-dir is required unless REVIEW_DIR is set")
    review_dir = resolve_review_dir(Path.cwd(), args.review_dir)
    raw_dir = Path(args.raw_dir) if args.raw_dir else review_dir / "raw-findings"
    out_path = Path(args.out) if args.out else review_dir / "dedupe-candidates.json"
    findings = list(iter_findings(raw_dir))
    index = build_candidate_index(findings, qualifying_severities=parse_severities(args.severity), min_findings=args.min_findings)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out_path),
                "input_finding_count": index["input_finding_count"],
                "qualifying_finding_count": index["qualifying_finding_count"],
                "skipped": index["skipped"],
                "candidate_pair_count": index["candidate_pair_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
