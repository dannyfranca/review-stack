#!/usr/bin/env python3
"""Create the deterministic review-stack inventory.

Purpose
-------
This script is a narrow helper, not a reviewer. It gathers the changed-file list,
full diff context, untracked file contents, and coarse routing hints so the
review_mapper agent can build semantic slices.

It is intentionally conservative:
- it writes only under the selected review directory;
- it never edits, deletes, stages, commits, or formats source files;
- it explicitly excludes review-state and common generated/vendor directories;
- it includes text contents for untracked files in synthetic diff form so local
  uncommitted work is reviewable.

The `slices.preliminary.json` output is only a seed for mapper context. It must
not be treated as the final review boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Sequence, Tuple
from review_common import (
    default_review_dir_for_session,
    generate_session_id,
    infer_session_id,
    posix_path,
    repo_relative_prefix,
    resolve_review_dir,
)

MAX_UNTRACKED_BYTES = 256_000
DEFAULT_EXCLUDE_PREFIXES = (
    ".git/",
    ".review/",
    ".review-sessions/",
    "node_modules/",
    "vendor/",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    "coverage/",
    ".next/",
    ".turbo/",
    ".cache/",
)


@dataclass(frozen=True)
class GitResult:
    stdout: str
    stderr: str
    returncode: int


def repo_root() -> Path:
    """Return the git repository root, or the current directory outside git."""
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return Path.cwd().resolve()


def run_git(args: Sequence[str], *, cwd: Path, check: bool = False) -> GitResult:
    """Run git in the repository root and return captured output."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return GitResult(proc.stdout.strip(), proc.stderr.strip(), proc.returncode)


def git_stdout(args: Sequence[str], *, cwd: Path, check: bool = False) -> str:
    return run_git(args, cwd=cwd, check=check).stdout


def first_existing_base(candidates: Iterable[str], *, cwd: Path) -> str:
    """Resolve a usable base ref from explicit and fallback candidates."""
    for cand in candidates:
        if not cand:
            continue
        proc = run_git(["rev-parse", "--verify", cand], cwd=cwd)
        if proc.returncode == 0:
            return cand
    upstream = git_stdout(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=cwd)
    if upstream:
        return upstream
    return "HEAD~1"


def merge_base(base: str, *, cwd: Path) -> str:
    mb = git_stdout(["merge-base", "HEAD", base], cwd=cwd)
    return mb or base


def normalize_prefix(prefix: str) -> str:
    prefix = prefix.replace("\\", "/").strip()
    if not prefix:
        return prefix
    if prefix.endswith("/"):
        return prefix
    # Treat exact file-like patterns as exact prefixes too. Directories should
    # be passed with trailing slash by callers.
    return prefix


def should_exclude(path: str, exclude_prefixes: Sequence[str]) -> bool:
    """Return True when the repo-relative path should not enter review scope."""
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    for raw in exclude_prefixes:
        prefix = normalize_prefix(raw)
        if not prefix:
            continue
        if prefix.endswith("/"):
            if p == prefix[:-1] or p.startswith(prefix):
                return True
        elif p == prefix or p.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def parse_name_status(text: str, source: str, exclude_prefixes: Sequence[str]) -> Dict[str, dict]:
    """Parse `git diff --name-status` output into file records.

    Handles rename/copy records by keeping the destination path as the reviewed
    path and preserving the raw status.
    """
    out: Dict[str, dict] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        if should_exclude(path, exclude_prefixes):
            continue
        out[path] = {"path": path, "status": status, "sources": [source]}
    return out


def classify_path(path: str) -> List[str]:
    """Return coarse routing tags from the file path.

    These tags only help choose which specialist agents may be useful. They are
    not semantic review slices and must not replace the mapper's reasoning.
    """
    p = path.lower()
    rules = [
        ("test", r"(^|/)(test|tests|spec|specs|__tests__)/|\.(test|spec)\."),
        ("migration", r"(^|/)(migration|migrations|schema|schemas|prisma|db|database)(/|$)|alembic|liquibase"),
        ("security", r"auth|session|permission|policy|rbac|acl|tenant|org|account|jwt|oauth|saml|secret|token|crypto|encrypt"),
        ("api_contract", r"(^|/)(api|routes|router|controllers|graphql|grpc|proto|openapi|webhook|client|sdk)(/|$)|schema|contract"),
        ("frontend", r"(^|/)(components|pages|app|ui|frontend|views|screens)(/|$)|\.(tsx|jsx|vue|svelte)$"),
        ("concurrency_perf", r"queue|worker|job|cron|cache|lock|mutex|async|thread|pool|stream|retry|rate|batch"),
        ("dependency", r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock|requirements.*\.txt|go\.sum|cargo\.lock|gemfile\.lock)$"),
        ("config_build_deploy", r"(^|/)(\.github|buildkite|dockerfile|docker-compose|terraform|infra|helm|k8s|deploy|ci|cd|config)(/|$)|\.ya?ml$|\.toml$"),
        ("docs", r"(^|/)(docs|documentation)(/|$)|\.md$"),
    ]
    tags = [tag for tag, pattern in rules if re.search(pattern, p)]
    return tags or ["general"]


def top_component(path: str) -> str:
    parts = PurePosixPath(path).parts
    if not parts:
        return "root"
    if len(parts) >= 2 and parts[0] in {"src", "app", "packages", "services", "apps", "libs"}:
        return "/".join(parts[:2])
    return parts[0]


def safe_slice_id(raw: str) -> str:
    raw = raw.strip("/").replace("/", "-")
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw)
    return raw[:80].strip("-") or "root"


def extract_hunk_headers(diff_text: str) -> Dict[str, List[str]]:
    """Return changed hunk headers per new file path."""
    current: str | None = None
    out: Dict[str, List[str]] = {}
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[len("+++ b/") :]
            out.setdefault(current, [])
        elif line.startswith("+++ /dev/null"):
            current = None
        elif line.startswith("@@") and current:
            parts = line.split("@@", 2)
            symbol = parts[2].strip() if len(parts) > 2 else line.strip()
            if symbol:
                out.setdefault(current, []).append(symbol[:160])
    return out


def likely_entrypoints(path: str, hunk_headers: Sequence[str]) -> List[str]:
    """Return cheap endpoint/symbol hints for the semantic mapper."""
    p = path.lower()
    hints: List[str] = []
    if re.search(r"(^|/)(api|routes|router|controllers|pages|app)(/|$)", p):
        hints.append(path)
    for h in hunk_headers:
        if re.search(r"\b(GET|POST|PUT|PATCH|DELETE|handler|route|controller|resolver|mutation|query|job|worker)\b", h, re.I):
            hints.append(h)
    return list(dict.fromkeys(hints))[:12]


def suggested_reviewers_for_tags(tags: Sequence[str]) -> List[str]:
    required = ["review_slice_context"]
    if "security" in tags:
        required.append("review_security")
    if "migration" in tags:
        required.append("review_data_migration")
    if "api_contract" in tags:
        required.append("review_contract_api")
    if "concurrency_perf" in tags:
        required.append("review_concurrency_perf")
    if "test" in tags:
        required.append("review_tests")
    return sorted(set(required))


def build_preliminary_slices(files: Sequence[dict]) -> List[dict]:
    """Group files into coarse seed buckets for the mapper.

    These are intentionally *not* review tasks. They give the mapper compact
    bundles of related files and risk tags, then the mapper creates real semantic
    slices such as individual endpoints, jobs, frontend flows, or migrations.
    """
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for f in files:
        tags = f.get("risk_tags", []) or ["general"]
        primary = tags[0]
        component = f.get("component") or top_component(f["path"])
        groups.setdefault((primary, component), []).append(f)

    slices: List[dict] = []
    for (primary, component), items in sorted(groups.items()):
        tags = sorted({tag for item in items for tag in item.get("risk_tags", [])})
        entrypoints: List[str] = []
        changed_symbols: List[str] = []
        for item in items:
            entrypoints.extend(item.get("entrypoint_hints", []))
            changed_symbols.extend(item.get("changed_hunks", []))
        sid = safe_slice_id(f"seed-{primary}-{component}")
        slices.append(
            {
                "id": sid,
                "title": f"seed {primary}: {component}",
                "preliminary": True,
                "intent": "Non-authoritative inventory seed. review_mapper must split this by changed behavior.",
                "primary_tag": primary,
                "component": component,
                "risk_tags": tags,
                "files": [x["path"] for x in items],
                "entrypoints": list(dict.fromkeys(entrypoints))[:24],
                "changed_symbols": list(dict.fromkeys(changed_symbols))[:50],
                "context_files": [],
                "suggested_reviewers": suggested_reviewers_for_tags(tags),
                "suggested_tests": [],
                "related_slices": [],
                "reason": (
                    f"{len(items)} changed file(s) under {component} tagged {', '.join(tags)}. "
                    "This is only a mapper seed, not a final semantic boundary."
                ),
            }
        )
    return slices


def is_probably_binary(data: bytes) -> bool:
    if b"\0" in data:
        return True
    # Small heuristic: if decoding fails badly, avoid dumping it into diff text.
    try:
        data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def synthetic_untracked_diff(repo: Path, path: str, *, max_bytes: int = MAX_UNTRACKED_BYTES) -> str:
    """Return a diff-like text block for an untracked file.

    Git does not include untracked files in `git diff`. This synthetic patch is
    enough for agents to review the new file contents in local, pre-commit flows.
    """
    file_path = (repo / path).resolve()
    try:
        if not file_path.is_file():
            return ""
        size = file_path.stat().st_size
        data = file_path.read_bytes()
    except OSError as exc:
        return f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+[untracked file unreadable: {exc}]\n"

    header = f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
    if size > max_bytes:
        return header + f"@@ -0,0 +1 @@\n+[untracked file omitted: size {size} exceeds {max_bytes} bytes]\n"
    if is_probably_binary(data):
        return header + f"@@ -0,0 +1 @@\n+[untracked binary file omitted: {size} bytes]\n"

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if text.endswith("\n"):
        # splitlines() discards final empty line; no extra marker required.
        pass
    body = [f"@@ -0,0 +1,{max(len(lines), 1)} @@"]
    if lines:
        body.extend("+" + line for line in lines)
    else:
        body.append("+")
    return header + "\n".join(body) + "\n"


def diff_text_for_files(repo: Path, base_ref: str, files: Sequence[str], untracked: Sequence[str]) -> str:
    """Return branch/staged/unstaged plus synthetic untracked diff for files."""
    chunks: List[str] = []
    tracked_files = [f for f in files if f not in set(untracked)]
    if tracked_files:
        branch_diff = git_stdout(["diff", f"{base_ref}...HEAD", "--", *tracked_files], cwd=repo)
        staged_diff = git_stdout(["diff", "--cached", "--", *tracked_files], cwd=repo)
        unstaged_diff = git_stdout(["diff", "--", *tracked_files], cwd=repo)
        if branch_diff:
            chunks.append(f"### branch diff ({base_ref}...HEAD)\n{branch_diff}\n")
        if staged_diff:
            chunks.append(f"### staged diff\n{staged_diff}\n")
        if unstaged_diff:
            chunks.append(f"### unstaged diff\n{unstaged_diff}\n")
    selected_untracked = [f for f in files if f in set(untracked)]
    if selected_untracked:
        chunks.append("### untracked file contents\n" + "\n".join(synthetic_untracked_diff(repo, f) for f in selected_untracked))
    return "\n".join(chunks).strip() + ("\n" if chunks else "")


def full_diff_text(repo: Path, base_ref: str, files: Sequence[str], untracked: Sequence[str]) -> str:
    """Return full review diff for the selected, non-excluded files only."""
    return diff_text_for_files(repo, base_ref, files, untracked)


def write_slice_diffs(repo: Path, review_dir: Path, base_ref: str, slices: Sequence[dict], untracked: Sequence[str]) -> None:
    out_dir = review_dir / "slice-diffs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for sl in slices:
        files = sl.get("files", [])
        text = diff_text_for_files(repo, base_ref, files, untracked)
        (out_dir / f"{sl['id']}.diff").write_text(text, encoding="utf-8")


def load_state_template(
    skill_dir: Path,
    now: str,
    base: str,
    mb: str,
    mode: str,
    max_loops: int,
    *,
    session_id: str,
    review_dir_label: str,
    repo: Path,
    head_sha: str,
) -> dict:
    template_path = skill_dir / "assets" / "state-template.json"
    state: dict
    if template_path.exists():
        try:
            state = json.loads(template_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}
    
    def pick(value: object, fallback: object) -> object:
        return value if value not in ("", None) else fallback

    state.update(
        {
            "version": state.get("version", 1),
            "session_id": pick(state.get("session_id"), session_id),
            "review_dir": pick(state.get("review_dir"), review_dir_label),
            "repo_root": pick(state.get("repo_root"), posix_path(repo)),
            "head_sha": pick(state.get("head_sha"), head_sha),
            "base": base,
            "merge_base": mb,
            "mode": mode,
            "current_loop": int(state.get("current_loop", 0)),
            "max_loops": max_loops,
            "started_at": state.get("started_at", now),
            "last_updated_at": now,
            "loops": state.get("loops", []),
            "canonical_findings": state.get("canonical_findings", []),
            "resolved_findings": state.get("resolved_findings", []),
            "manual_review": state.get("manual_review", []),
            "deterministic_checks": state.get("deterministic_checks", []),
            "stop_reason": state.get("stop_reason", ""),
        }
    )
    return state


def collect_untracked(repo: Path, exclude_prefixes: Sequence[str]) -> List[str]:
    text = git_stdout(["ls-files", "--others", "--exclude-standard"], cwd=repo)
    paths = []
    for raw in text.splitlines():
        path = raw.strip()
        if path and not should_exclude(path, exclude_prefixes):
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def combine_file_records(repo: Path, mb: str, untracked: Sequence[str], exclude_prefixes: Sequence[str]) -> Dict[str, dict]:
    combined: Dict[str, dict] = {}
    sources = [
        ("branch", ["diff", "--name-status", f"{mb}...HEAD"]),
        ("staged", ["diff", "--name-status", "--cached"]),
        ("unstaged", ["diff", "--name-status"]),
    ]
    for source, git_args in sources:
        for path, rec in parse_name_status(git_stdout(git_args, cwd=repo), source, exclude_prefixes).items():
            if path in combined:
                combined[path]["sources"].extend(rec["sources"])
                combined[path]["status"] = combined[path]["status"] + "+" + rec["status"]
            else:
                combined[path] = rec
    for path in untracked:
        combined.setdefault(path, {"path": path, "status": "??", "sources": []})["sources"].append("untracked")
    return combined


def parse_exclude_prefixes(extra: Sequence[str] | None) -> List[str]:
    prefixes = list(DEFAULT_EXCLUDE_PREFIXES)
    for item in extra or []:
        prefixes.extend(x.strip() for x in item.split(",") if x.strip())
    return prefixes


def choose_review_dir(repo: Path, requested_review_dir: str | None, mode: str) -> tuple[Path, str, str, bool]:
    if requested_review_dir:
        review_dir_label = requested_review_dir
        session_id = infer_session_id(review_dir_label, mode)
        allocated = False
    else:
        session_id = generate_session_id(mode)
        review_dir_label = default_review_dir_for_session(session_id)
        allocated = True
    return resolve_review_dir(repo, review_dir_label), review_dir_label, session_id, allocated


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create review inventory for review-stack")
    ap.add_argument("--base", default=os.environ.get("REVIEW_BASE", "origin/main"))
    ap.add_argument("--mode", choices=["audit", "fix"], default=os.environ.get("REVIEW_MODE", "audit"))
    ap.add_argument("--max-loops", type=int, default=int(os.environ.get("REVIEW_MAX_LOOPS", "6")))
    ap.add_argument("--review-dir", default=os.environ.get("REVIEW_DIR"))
    ap.add_argument(
        "--exclude-prefix",
        action="append",
        default=[],
        help="Additional repo-relative path prefix to exclude. May be repeated or comma-separated.",
    )
    args = ap.parse_args(argv)

    repo = repo_root()
    review_dir, review_dir_label, session_id, allocated_review_dir = choose_review_dir(repo, args.review_dir, args.mode)
    skill_dir = Path(__file__).resolve().parents[1]
    exclude_prefixes = parse_exclude_prefixes(args.exclude_prefix)
    active_prefix = repo_relative_prefix(repo, review_dir)
    if active_prefix and active_prefix not in exclude_prefixes:
        exclude_prefixes.append(active_prefix)

    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "slice-diffs").mkdir(parents=True, exist_ok=True)

    base = first_existing_base([args.base, "origin/main", "main", "master"], cwd=repo)
    mb = merge_base(base, cwd=repo)
    head_sha = git_stdout(["rev-parse", "HEAD"], cwd=repo)
    untracked = collect_untracked(repo, exclude_prefixes)
    combined = combine_file_records(repo, mb, untracked, exclude_prefixes)
    full_diff = full_diff_text(repo, mb, list(combined.keys()), untracked)
    hunk_headers = extract_hunk_headers(full_diff)

    files: List[dict] = []
    for path, rec in sorted(combined.items()):
        tags = classify_path(path)
        hunks = hunk_headers.get(path, [])
        files.append(
            {
                **rec,
                "risk_tags": tags,
                "component": top_component(path),
                "changed_hunks": hunks,
                "entrypoint_hints": likely_entrypoints(path, hunks),
            }
        )

    preliminary_slices = build_preliminary_slices(files)
    write_slice_diffs(repo, review_dir, mb, preliminary_slices, untracked)

    stat = git_stdout(["diff", "--stat", f"{mb}...HEAD"], cwd=repo)
    numstat = git_stdout(["diff", "--numstat", f"{mb}...HEAD"], cwd=repo)
    now = datetime.now(timezone.utc).isoformat()

    inventory = {
        "generated_at": now,
        "session_id": session_id,
        "review_dir": review_dir_label,
        "repo_root": posix_path(repo),
        "head_sha": head_sha,
        "base_requested": args.base,
        "base_resolved": base,
        "merge_base": mb,
        "mode": args.mode,
        "file_count": len(files),
        "files": files,
        "untracked_files_included": list(untracked),
        "excluded_prefixes": list(exclude_prefixes),
        "risk_tags": sorted({tag for f in files for tag in f["risk_tags"]}),
        "diff_stat": stat,
        "diff_numstat": numstat,
        "full_diff_path": posix_path(review_dir / "full.diff"),
        "preliminary_slices_path": posix_path(review_dir / "slices.preliminary.json"),
        "semantic_slices_path": posix_path(review_dir / "semantic-slices.json"),
        "note": "Preliminary slices are deterministic inventory seeds. review_mapper must create semantic-slices.json before review.",
    }

    (review_dir / "full.diff").write_text(full_diff, encoding="utf-8")
    (review_dir / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (review_dir / "slices.preliminary.json").write_text(
        json.dumps({"generated_at": now, "slices": preliminary_slices}, indent=2), encoding="utf-8"
    )

    state_path = review_dir / "state.json"
    if not state_path.exists():
        state = load_state_template(
            skill_dir,
            now,
            base,
            mb,
            args.mode,
            args.max_loops,
            session_id=session_id,
            review_dir_label=review_dir_label,
            repo=repo,
            head_sha=head_sha,
        )
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        state.update(
            {
                "session_id": state.get("session_id") or session_id,
                "review_dir": state.get("review_dir") or review_dir_label,
                "repo_root": state.get("repo_root") or posix_path(repo),
                "head_sha": head_sha,
                "base": base,
                "merge_base": mb,
                "mode": args.mode,
                "last_updated_at": now,
                "max_loops": args.max_loops,
            }
        )
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "session_id": state.get("session_id") or session_id,
                "review_dir": state.get("review_dir") or review_dir_label,
                "review_dir_allocated": allocated_review_dir,
                "inventory": posix_path(review_dir / "inventory.json"),
                "preliminary_slices": posix_path(review_dir / "slices.preliminary.json"),
                "semantic_slices": posix_path(review_dir / "semantic-slices.json"),
                "full_diff": posix_path(review_dir / "full.diff"),
                "state": posix_path(state_path),
                "file_count": len(files),
                "untracked_file_count": len(untracked),
                "preliminary_slice_count": len(preliminary_slices),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
