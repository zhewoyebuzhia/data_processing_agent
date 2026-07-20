"""Long-running local worker that gives every collection job its own interval."""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOBS_FILE = PROJECT_ROOT / "config" / "collection_jobs.json"
RUNNER_FILE = PROJECT_ROOT / "src" / "core" / "run_collection_tool.py"
LOG_FILE = PROJECT_ROOT / "logs" / "collection_worker.log"


def load_jobs():
    try:
        jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return jobs if isinstance(jobs, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"{datetime.now().isoformat(timespec='seconds')} | {message}\n")


def run_job(job: dict) -> None:
    tool_path = job.get("tool_path")
    if not isinstance(tool_path, str):
        return
    try:
        result = subprocess.run(
            [sys.executable, str(RUNNER_FILE), tool_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode:
            log(f"ERROR {job.get('name')}: {result.stderr.strip() or result.stdout.strip()}")
        else:
            log(f"OK {job.get('name')}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"ERROR {job.get('name')}: {exc}")


def main() -> None:
    os_last_run = {}
    while True:
        now = time.monotonic()
        for job in load_jobs():
            if not job.get("enabled", True):
                continue
            interval = job.get("interval_seconds")
            name = job.get("name")
            if not isinstance(name, str) or not isinstance(interval, int) or interval < 1:
                continue
            if now - os_last_run.get(name, float("-inf")) >= interval:
                run_job(job)
                os_last_run[name] = time.monotonic()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
