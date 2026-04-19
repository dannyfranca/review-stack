#!/usr/bin/env python3
"""Small state helper for review-stack."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

STATE = Path('.review/state.json')

def load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {
        'version': 1,
        'base': 'origin/main',
        'mode': 'audit',
        'current_loop': 0,
        'max_loops': 6,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'last_updated_at': datetime.now(timezone.utc).isoformat(),
        'loops': [],
        'canonical_findings': [],
        'resolved_findings': [],
        'manual_review': [],
        'deterministic_checks': [],
        'stop_reason': '',
    }

def save(state):
    STATE.parent.mkdir(exist_ok=True)
    state['last_updated_at'] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('show')
    p = sub.add_parser('start-loop')
    p.add_argument('--note', default='')
    p = sub.add_parser('finish-loop')
    p.add_argument('--new-confirmed', type=int, default=0)
    p.add_argument('--remaining-confirmed', type=int, default=0)
    p.add_argument('--fixes-applied', type=int, default=0)
    p.add_argument('--note', default='')
    p = sub.add_parser('stop')
    p.add_argument('reason')
    args = ap.parse_args()

    state = load()
    if args.cmd == 'show':
        print(json.dumps(state, indent=2))
        return 0
    if args.cmd == 'start-loop':
        state['current_loop'] = int(state.get('current_loop', 0)) + 1
        state.setdefault('loops', []).append({
            'loop': state['current_loop'],
            'started_at': datetime.now(timezone.utc).isoformat(),
            'note': args.note,
            'new_confirmed': None,
            'remaining_confirmed': None,
            'fixes_applied': None,
        })
        save(state)
        print(json.dumps({'current_loop': state['current_loop']}, indent=2))
        return 0
    if args.cmd == 'finish-loop':
        if not state.get('loops'):
            state['loops'] = [{'loop': state.get('current_loop', 1)}]
        loop = state['loops'][-1]
        loop.update({
            'finished_at': datetime.now(timezone.utc).isoformat(),
            'new_confirmed': args.new_confirmed,
            'remaining_confirmed': args.remaining_confirmed,
            'fixes_applied': args.fixes_applied,
            'note': args.note,
        })
        save(state)
        print(json.dumps(loop, indent=2))
        return 0
    if args.cmd == 'stop':
        state['stop_reason'] = args.reason
        save(state)
        print(json.dumps({'stop_reason': args.reason}, indent=2))
        return 0
    return 2

if __name__ == '__main__':
    raise SystemExit(main())
