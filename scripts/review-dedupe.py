#!/usr/bin/env python3
"""Merge raw review-stack findings by simple root-cause heuristics."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable

REVIEW_DIR = Path('.review')

def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r'`[^`]+`', ' symbol ', s)
    s = re.sub(r'[^a-z0-9_/.-]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def key_for(f: Dict[str, Any]) -> str:
    file = f.get('file', '')
    symbolish = ' '.join([f.get('category',''), f.get('claim',''), f.get('title','')])
    root = norm(symbolish)[:180]
    primary = f'{f.get("category","unknown")}|{file}|{root}'
    return hashlib.sha1(primary.encode('utf-8')).hexdigest()[:12]

def iter_findings(raw_dir: Path) -> Iterable[Dict[str, Any]]:
    for path in sorted(raw_dir.glob('**/*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        findings = data.get('findings') if isinstance(data, dict) else None
        if not isinstance(findings, list):
            continue
        for f in findings:
            if not isinstance(f, dict):
                continue
            f = dict(f)
            f['_source_file'] = str(path)
            f['_source_agent'] = data.get('agent', path.stem)
            yield f

def severity_rank(sev: str) -> int:
    return {'blocking': 5, 'important': 4, 'question': 3, 'nit': 2, 'pre_existing': 1}.get(sev, 0)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-dir', default=str(REVIEW_DIR / 'raw-findings'))
    ap.add_argument('--out', default=str(REVIEW_DIR / 'deduped-findings.json'))
    args = ap.parse_args()

    clusters: Dict[str, Dict[str, Any]] = {}
    for f in iter_findings(Path(args.raw_dir)):
        k = key_for(f)
        if k not in clusters:
            clusters[k] = {'id': k, 'canonical': f, 'duplicates': [], 'sources': []}
        c = clusters[k]
        c['duplicates'].append(f)
        c['sources'].append({'agent': f.get('_source_agent'), 'file': f.get('_source_file')})
        if severity_rank(f.get('severity','')) > severity_rank(c['canonical'].get('severity','')) or f.get('confidence',0) > c['canonical'].get('confidence',0):
            c['canonical'] = f

    out = {
        'cluster_count': len(clusters),
        'clusters': sorted(clusters.values(), key=lambda c: (-severity_rank(c['canonical'].get('severity','')), -float(c['canonical'].get('confidence',0))))
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps({'out': args.out, 'cluster_count': len(clusters)}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
