"""Per-job scheduling for agent-generated local collection tools."""
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from config.settings import BASE_DIR, TOOLS_DIR


class CollectionScheduler:
    """Persist independent intervals and keep one local collection worker running."""

    WORKER_TASK_NAME = "DataProcessingAgent_CollectionWorker"
    JOBS_FILE = BASE_DIR / "config" / "collection_jobs.json"
    WORKER_FILE = BASE_DIR / "src" / "core" / "collection_worker.py"

    def __init__(self):
        self.logger = None

    def set_logger(self, logger):
        self.logger = logger

    def register(self, tool_path: str, device_name: str, interval_seconds: int) -> Tuple[bool, str]:
        """Register a tool with its own interval, in seconds, then start the worker."""
        if not 1 <= interval_seconds <= 31 * 24 * 60 * 60:
            return False, "采集间隔必须在 1 秒到 31 天之间。"

        path = Path(tool_path).resolve()
        try:
            relative_tool_path = path.relative_to(TOOLS_DIR.resolve())
        except ValueError:
            return False, "只能为 tools/ 目录中的采集工具创建定时任务。"

        safe_device = re.sub(r"[^A-Za-z0-9_-]", "_", device_name)
        safe_tool = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)
        job_name = f"{safe_device}_{safe_tool}"
        self._record_job(job_name, relative_tool_path, device_name, interval_seconds)
        started, message = self._ensure_worker_running()
        if started and self.logger:
            self.logger.info(f"✅ 已注册独立采集任务: {job_name} ({interval_seconds}s)")
        return started, message

    def _record_job(self, job_name: str, tool_path: Path, device_name: str, interval_seconds: int) -> None:
        self.JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            jobs = json.loads(self.JOBS_FILE.read_text(encoding="utf-8")) if self.JOBS_FILE.exists() else []
        except (json.JSONDecodeError, OSError):
            jobs = []
        if not isinstance(jobs, list):
            jobs = []

        job = {
            "name": job_name,
            "tool_path": str(Path("tools") / tool_path),
            "device": device_name,
            "interval_seconds": interval_seconds,
            "enabled": True,
        }
        jobs = [item for item in jobs if item.get("name") != job_name]
        jobs.append(job)
        temporary_file = self.JOBS_FILE.with_suffix(".tmp")
        temporary_file.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_file.replace(self.JOBS_FILE)

    def _ensure_worker_running(self) -> Tuple[bool, str]:
        """Create an on-logon worker and start it now for the current session."""
        task_command = f'"{sys.executable}" "{self.WORKER_FILE}"'
        create_command = [
            "schtasks", "/Create", "/TN", self.WORKER_TASK_NAME, "/TR", task_command,
            "/SC", "ONLOGON", "/F",
        ]
        try:
            created = subprocess.run(create_command, capture_output=True, text=True, timeout=30)
            if created.returncode != 0:
                return False, created.stderr.strip() or created.stdout.strip()
            started = subprocess.run(
                ["schtasks", "/Run", "/TN", self.WORKER_TASK_NAME],
                capture_output=True, text=True, timeout=30,
            )
            if started.returncode != 0:
                return False, started.stderr.strip() or started.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"启动本地采集 Worker 失败：{exc}"
        return True, self.WORKER_TASK_NAME
