#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

paths = [
    Path('.review/state.json'),
    Path('.review/inventory.json'),
    Path('.review/slices.preliminary.json'),
    Path('.review/semantic-slices.json'),
    Path('.review/deduped-findings.json'),
]

for path in paths:
    print(f'## {path}')
    if not path.exists():
        print('missing')
        print()
        continue
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'invalid json: {exc}')
        print()
        continue

    if path.name == 'state.json':
        print(json.dumps({k: data.get(k) for k in ['base','mode','current_loop','max_loops','stop_reason']}, indent=2))
        print(f"loops: {len(data.get('loops', []))}")
        print(f"manual_review: {len(data.get('manual_review', []))}")
        print(f"resolved_findings: {len(data.get('resolved_findings', []))}")
    elif path.name == 'inventory.json':
        print(json.dumps({k: data.get(k) for k in ['base_resolved','merge_base','file_count','risk_tags','full_diff_path']}, indent=2))
    elif path.name in {'slices.preliminary.json', 'semantic-slices.json'}:
        slices = data.get('slices', [])
        print(json.dumps({'slice_count': len(slices), 'slice_ids': [s.get('id') for s in slices[:20]]}, indent=2))
    else:
        print(json.dumps({k: data.get(k) for k in ['cluster_count']}, indent=2))
    print()
