from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def init_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "test@example.com"], root)
    run(["git", "config", "user.name", "Test User"], root)
    (root / "app.py").write_text("def existing():\n    return 1\n", encoding="utf-8")
    run(["git", "add", "app.py"], root)
    run(["git", "commit", "-m", "base"], root)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def python_script(name: str) -> list[str]:
    return [sys.executable, str(SCRIPTS / name)]
