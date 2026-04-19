#!/usr/bin/env python3
"""Shared helpers for review-stack bookkeeping scripts."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DEFAULT_SESSION_ROOT = ".review-sessions"


def posix_path(path: str | Path) -> str:
    return Path(path).as_posix()


def resolve_review_dir(repo: Path, review_dir: str) -> Path:
    path = Path(review_dir)
    if path.is_absolute():
        return path
    return (repo / path).resolve()


def generate_session_id(mode: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{mode}-{secrets.token_hex(3)}"


def default_review_dir_for_session(session_id: str) -> str:
    return posix_path(PurePosixPath(DEFAULT_SESSION_ROOT) / session_id)


def infer_session_id(review_dir: str, mode: str) -> str:
    pure = PurePosixPath(review_dir)
    parts = pure.parts
    if len(parts) >= 2 and parts[0] == DEFAULT_SESSION_ROOT.strip("/"):
        return parts[-1]
    raw = parts[-1] if parts else review_dir
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-")
    return raw or f"{mode}-session"


def repo_relative_prefix(repo: Path, target: Path) -> str | None:
    try:
        rel = target.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    text = posix_path(rel)
    if not text or text == ".":
        return None
    return text if text.endswith("/") else text + "/"
