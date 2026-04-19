#!/usr/bin/env python3
"""Build .review inventory and preliminary slices for review-stack.

This script is intentionally dependency-free. It writes only under .review/.
The preliminary slices are deterministic seeds. The review_mapper agent must
refine them into semantic slices before the review wave.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REVIEW_DIR = Path('.review')
SKILL_DIR = Path(__file__).resolve().parents[1]


def run_git(args: List[str], check: bool = False) -> str:
    proc = subprocess.run(['git', *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def first_existing_base(candidates: Iterable[str]) -> str:
    for cand in candidates:
        if not cand:
            continue
        proc = subprocess.run(['git', 'rev-parse', '--verify', cand], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0:
            return cand
    upstream = run_git(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'])
    if upstream:
        return upstream
    return 'HEAD~1'


def merge_base(base: str) -> str:
    mb = run_git(['merge-base', 'HEAD', base])
    return mb or base


def parse_name_status(text: str, source: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        status = parts[0]
        path = parts[-1]
        out[path] = {'path': path, 'status': status, 'sources': [source]}
    return out


def classify_path(path: str) -> List[str]:
    p = path.lower()
    tags = []
    rules = [
        ('test', r'(^|/)(test|tests|spec|specs|__tests__)/|\.(test|spec)\.'),
        ('migration', r'(^|/)(migration|migrations|schema|schemas|prisma|db|database)(/|$)|alembic|liquibase'),
        ('security', r'auth|session|permission|policy|rbac|acl|tenant|org|account|jwt|oauth|saml|secret|token|crypto|encrypt'),
        ('api_contract', r'(^|/)(api|routes|router|controllers|graphql|grpc|proto|openapi|webhook|client|sdk)(/|$)|schema|contract'),
        ('frontend', r'(^|/)(components|pages|app|ui|frontend|views|screens)(/|$)|\.(tsx|jsx|vue|svelte)$'),
        ('concurrency_perf', r'queue|worker|job|cron|cache|lock|mutex|async|thread|pool|stream|retry|rate|batch'),
        ('dependency', r'(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock|requirements.*\.txt|go\.sum|cargo\.lock|gemfile\.lock)$'),
        ('config_build_deploy', r'(^|/)(\.github|buildkite|dockerfile|docker-compose|terraform|infra|helm|k8s|deploy|ci|cd|config)(/|$)|\.ya?ml$|\.toml$'),
        ('docs', r'(^|/)(docs|documentation)(/|$)|\.md$'),
    ]
    for tag, pattern in rules:
        if re.search(pattern, p):
            tags.append(tag)
    if not tags:
        tags.append('general')
    return tags


def top_component(path: str) -> str:
    parts = Path(path).parts
    if not parts:
        return 'root'
    if len(parts) >= 2 and parts[0] in {'src', 'app', 'packages', 'services', 'apps', 'libs'}:
        return '/'.join(parts[:2])
    return parts[0]


def safe_slice_id(raw: str) -> str:
    raw = raw.strip('/').replace('/', '-')
    raw = re.sub(r'[^a-zA-Z0-9_.-]+', '-', raw)
    return raw[:80].strip('-') or 'root'


def extract_hunk_headers(diff_text: str) -> Dict[str, List[str]]:
    """Return changed hunk headers per new file path.

    This is intentionally simple and language-agnostic. The mapper performs the
    real semantic separation.
    """
    current: str | None = None
    out: Dict[str, List[str]] = {}
    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            current = line[len('+++ b/'):]
            out.setdefault(current, [])
        elif line.startswith('+++ /dev/null'):
            current = None
        elif line.startswith('@@') and current:
            # Capture the optional symbol text after the second @@.
            parts = line.split('@@', 2)
            symbol = parts[2].strip() if len(parts) > 2 else line.strip()
            if symbol:
                out.setdefault(current, []).append(symbol[:160])
    return out


def likely_entrypoints(path: str, hunk_headers: List[str]) -> List[str]:
    p = path.lower()
    hints: List[str] = []
    if re.search(r'(^|/)(api|routes|router|controllers|pages|app)(/|$)', p):
        hints.append(path)
    for h in hunk_headers:
        # Common route/function markers. This is not authoritative; mapper refines it.
        if re.search(r'\b(GET|POST|PUT|PATCH|DELETE|handler|route|controller|resolver|mutation|query|job|worker)\b', h, re.I):
            hints.append(h)
    return list(dict.fromkeys(hints))[:12]


def required_reviewers_for_tags(tags: List[str]) -> List[str]:
    required = ['review_slice_context']
    if 'security' in tags:
        required.append('review_security')
    if 'migration' in tags:
        required.append('review_data_migration')
    if 'api_contract' in tags:
        required.append('review_contract_api')
    if 'concurrency_perf' in tags:
        required.append('review_concurrency_perf')
    if 'test' in tags:
        required.append('review_tests')
    return sorted(set(required))


def build_preliminary_slices(files: List[dict]) -> List[dict]:
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for f in files:
        tags = f['risk_tags']
        primary = tags[0] if tags else 'general'
        component = f['component']
        groups.setdefault((primary, component), []).append(f)

    slices = []
    for (primary, component), items in sorted(groups.items()):
        tags = sorted({tag for item in items for tag in item['risk_tags']})
        entrypoints = []
        changed_symbols = []
        for item in items:
            entrypoints.extend(item.get('entrypoint_hints', []))
            changed_symbols.extend(item.get('changed_hunks', []))
        sid = safe_slice_id(f'{primary}-{component}')
        slices.append({
            'id': sid,
            'title': f'preliminary {primary}: {component}',
            'preliminary': True,
            'intent': 'Deterministic seed slice. review_mapper must refine this into semantic behavior slices.',
            'primary_tag': primary,
            'component': component,
            'risk_tags': tags,
            'files': [x['path'] for x in items],
            'entrypoints': list(dict.fromkeys(entrypoints))[:24],
            'changed_symbols': list(dict.fromkeys(changed_symbols))[:50],
            'context_files': [],
            'required_reviewers': required_reviewers_for_tags(tags),
            'suggested_tests': [],
            'related_slices': [],
            'reason': f'{len(items)} changed file(s) under {component} tagged {", ".join(tags)}. This is not a final semantic boundary.',
        })
    return slices


def full_diff_text(base_ref: str) -> str:
    chunks = []
    branch_diff = run_git(['diff', f'{base_ref}...HEAD'])
    staged_diff = run_git(['diff', '--cached'])
    unstaged_diff = run_git(['diff'])
    if branch_diff:
        chunks.append(f'### branch diff ({base_ref}...HEAD)\n{branch_diff}\n')
    if staged_diff:
        chunks.append(f'### staged diff\n{staged_diff}\n')
    if unstaged_diff:
        chunks.append(f'### unstaged diff\n{unstaged_diff}\n')
    return '\n'.join(chunks)


def write_slice_diffs(base_ref: str, slices: List[dict]) -> None:
    out_dir = REVIEW_DIR / 'slice-diffs'
    out_dir.mkdir(parents=True, exist_ok=True)
    for sl in slices:
        files = sl['files']
        chunks = []
        if files:
            branch_diff = run_git(['diff', f'{base_ref}...HEAD', '--', *files])
            staged_diff = run_git(['diff', '--cached', '--', *files])
            unstaged_diff = run_git(['diff', '--', *files])
            if branch_diff:
                chunks.append(f'### branch diff ({base_ref}...HEAD)\n{branch_diff}\n')
            if staged_diff:
                chunks.append(f'### staged diff\n{staged_diff}\n')
            if unstaged_diff:
                chunks.append(f'### unstaged diff\n{unstaged_diff}\n')
        (out_dir / f"{sl['id']}.diff").write_text('\n'.join(chunks), encoding='utf-8')


def load_state_template(now: str, base: str, mb: str, mode: str, max_loops: int) -> dict:
    template_path = SKILL_DIR / 'assets' / 'state-template.json'
    if template_path.exists():
        try:
            state = json.loads(template_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}
    state.update({
        'version': state.get('version', 1),
        'base': base,
        'merge_base': mb,
        'mode': mode,
        'current_loop': 0,
        'max_loops': max_loops,
        'started_at': now,
        'last_updated_at': now,
        'loops': state.get('loops', []),
        'canonical_findings': state.get('canonical_findings', []),
        'resolved_findings': state.get('resolved_findings', []),
        'manual_review': state.get('manual_review', []),
        'deterministic_checks': state.get('deterministic_checks', []),
        'stop_reason': state.get('stop_reason', ''),
    })
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('REVIEW_BASE', 'origin/main'))
    ap.add_argument('--mode', choices=['audit', 'fix'], default=os.environ.get('REVIEW_MODE', 'audit'))
    ap.add_argument('--max-loops', type=int, default=int(os.environ.get('REVIEW_MAX_LOOPS', '6')))
    args = ap.parse_args()

    REVIEW_DIR.mkdir(exist_ok=True)

    base = first_existing_base([args.base, 'origin/main', 'main', 'master'])
    mb = merge_base(base)
    full_diff = full_diff_text(mb)
    hunk_headers = extract_hunk_headers(full_diff)

    combined: Dict[str, dict] = {}
    sources = [
        ('branch', ['diff', '--name-status', f'{mb}...HEAD']),
        ('staged', ['diff', '--name-status', '--cached']),
        ('unstaged', ['diff', '--name-status']),
    ]
    for source, git_args in sources:
        for path, rec in parse_name_status(run_git(git_args), source).items():
            if path in combined:
                combined[path]['sources'].extend(rec['sources'])
                combined[path]['status'] = combined[path]['status'] + '+' + rec['status']
            else:
                combined[path] = rec

    untracked = run_git(['ls-files', '--others', '--exclude-standard'])
    for path in untracked.splitlines():
        if path.strip():
            combined.setdefault(path, {'path': path, 'status': '??', 'sources': []})['sources'].append('untracked')

    files = []
    for path, rec in sorted(combined.items()):
        tags = classify_path(path)
        hunks = hunk_headers.get(path, [])
        files.append({
            **rec,
            'risk_tags': tags,
            'component': top_component(path),
            'changed_hunks': hunks,
            'entrypoint_hints': likely_entrypoints(path, hunks),
        })

    preliminary_slices = build_preliminary_slices(files)
    write_slice_diffs(mb, preliminary_slices)

    stat = run_git(['diff', '--stat', f'{mb}...HEAD'])
    numstat = run_git(['diff', '--numstat', f'{mb}...HEAD'])
    now = datetime.now(timezone.utc).isoformat()

    inventory = {
        'generated_at': now,
        'base_requested': args.base,
        'base_resolved': base,
        'merge_base': mb,
        'mode': args.mode,
        'file_count': len(files),
        'files': files,
        'risk_tags': sorted({tag for f in files for tag in f['risk_tags']}),
        'diff_stat': stat,
        'diff_numstat': numstat,
        'full_diff_path': str(REVIEW_DIR / 'full.diff'),
        'preliminary_slices_path': str(REVIEW_DIR / 'slices.preliminary.json'),
        'semantic_slices_path': str(REVIEW_DIR / 'semantic-slices.json'),
    }

    (REVIEW_DIR / 'full.diff').write_text(full_diff, encoding='utf-8')
    (REVIEW_DIR / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    (REVIEW_DIR / 'slices.preliminary.json').write_text(json.dumps({'generated_at': now, 'slices': preliminary_slices}, indent=2), encoding='utf-8')
    # Backward compatibility for earlier prompts/tools.
    (REVIEW_DIR / 'slices.json').write_text(json.dumps({'generated_at': now, 'slices': preliminary_slices}, indent=2), encoding='utf-8')

    state_path = REVIEW_DIR / 'state.json'
    if not state_path.exists():
        state = load_state_template(now, base, mb, args.mode, args.max_loops)
    else:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state.update({'base': base, 'merge_base': mb, 'mode': args.mode, 'last_updated_at': now, 'max_loops': args.max_loops})
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')

    print(json.dumps({
        'inventory': str(REVIEW_DIR / 'inventory.json'),
        'preliminary_slices': str(REVIEW_DIR / 'slices.preliminary.json'),
        'semantic_slices': str(REVIEW_DIR / 'semantic-slices.json'),
        'full_diff': str(REVIEW_DIR / 'full.diff'),
        'state': str(state_path),
        'file_count': len(files),
        'preliminary_slice_count': len(preliminary_slices),
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
