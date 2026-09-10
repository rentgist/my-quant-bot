from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_DIR = ROOT / ".ai-company"
TASKS_DIR = AI_DIR / "tasks"
HANDOFFS_DIR = AI_DIR / "handoffs"
LOGS_DIR = AI_DIR / "logs"


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def ensure_clean_repo() -> None:
    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if status:
        raise RuntimeError("Working tree is not clean. Commit/stash local changes before running the worker.")


def parse_task(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {"body": text}
    for key in ["STATUS", "OWNER", "WORKFLOW", "NEXT_AGENT"]:
        m = re.search(rf"(?mi)^\s*{key}\s*:\s*(.+?)\s*$", text)
        if m:
            out[key.lower()] = m.group(1).strip()
    out["id"] = path.stem
    return out


def find_ready_task(explicit: str | None) -> Path:
    if explicit:
        p = TASKS_DIR / f"{explicit}.md"
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    for p in sorted(TASKS_DIR.glob("TASK-*.md")):
        task = parse_task(p)
        if task.get("status", "").upper() == "READY" and task.get("owner", "").upper() == "CODEX":
            return p
    raise RuntimeError("No READY task owned by CODEX.")


def codex_version() -> str:
    cp = run(["codex", "--version"])
    return cp.stdout.strip() or cp.stderr.strip()


def build_prompt(task_path: Path) -> str:
    return f"""You are the CODEX Developer in AI Company OS for this repository.

Before working, read these files if present:
- AGENTS.md
- AI_CONTEXT.md
- .agents/AGENTS.md
- .agents/rules/strict_verification.md
- .ai-company/CONSTITUTION.md
- .ai-company/PERMISSIONS.md
- .ai-company/WORKFLOWS.md
- {task_path.relative_to(ROOT).as_posix()}

Execute ONLY the task in {task_path.name}.
Do not use paid APIs or reveal secrets.
Do not place trades or access brokerage accounts.
Respect the task's no-code-change constraint if present.
Record the requested repository artifacts directly in the working tree.
At the end, give a concise handoff containing: completed work, validation performed, remaining issues, NEXT_ACTION, OWNER.
"""


def run_task(task_path: Path) -> int:
    task_id = task_path.stem
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = HANDOFFS_DIR / f"{task_id}-CODEX.md"
    log_file = LOGS_DIR / f"{task_id}-codex.log"

    prompt = build_prompt(task_path)
    cmd = [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "-C",
        str(ROOT),
        "-o",
        str(output_file),
        prompt,
    ]
    print(f"Codex: {codex_version()}")
    cp = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    log_file.write_text((cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or ""), encoding="utf-8")
    print(cp.stdout)
    if cp.returncode != 0:
        print(cp.stderr, file=sys.stderr)
        return cp.returncode

    print(f"Task completed locally: {task_id}")
    print(f"Handoff: {output_file.relative_to(ROOT)}")
    print("Review git diff, then commit/push from the task branch.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Company OS Primary Worker")
    parser.add_argument("--task", help="Run a specific task id, e.g. TASK-001")
    parser.add_argument("--skip-clean-check", action="store_true")
    args = parser.parse_args()

    if not (ROOT / ".git").exists():
        raise RuntimeError("Run this from a git clone of my-quant-bot.")
    if not args.skip_clean_check:
        ensure_clean_repo()
    if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        print("WARNING: API key environment variable detected. This worker does not use API keys; Codex CLI subscription login is expected.")

    task_path = find_ready_task(args.task)
    return run_task(task_path)


if __name__ == "__main__":
    raise SystemExit(main())
