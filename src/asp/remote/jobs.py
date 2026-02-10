"""Job handle and registry for tracking remote job submissions.

Stores job metadata in .asp/jobs.yaml within the project directory.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asp.helpers import load_yaml, save_yaml


@dataclass
class JobHandle:
    """Metadata for a submitted remote job."""

    job_id: str
    cluster: str
    universe_id: str
    remote_job_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, UNKNOWN
    workdir: str
    submitted_at: str
    analysis_name: str = ""
    chunk_id: str = ""

    @staticmethod
    def create(
        cluster: str,
        universe_id: str,
        remote_job_id: str,
        workdir: str,
        analysis_name: str = "",
        chunk_id: str = "",
    ) -> JobHandle:
        """Create a new job handle with generated ID and timestamp."""
        return JobHandle(
            job_id=uuid.uuid4().hex[:12],
            cluster=cluster,
            universe_id=universe_id,
            remote_job_id=remote_job_id,
            status="PENDING",
            workdir=workdir,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            analysis_name=analysis_name,
            chunk_id=chunk_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> JobHandle:
        return JobHandle(**data)


class JobRegistry:
    """Reads/writes job handles to .asp/jobs.yaml."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._jobs_dir = project_dir / ".asp"
        self._jobs_file = self._jobs_dir / "jobs.yaml"

    def _load(self) -> dict[str, Any]:
        """Load the jobs file, or return empty structure."""
        if not self._jobs_file.exists():
            return {"jobs": []}
        data = load_yaml(self._jobs_file)
        if data is None:
            return {"jobs": []}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        """Save the jobs file."""
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        save_yaml(data, self._jobs_file)

    def add(self, job: JobHandle) -> None:
        """Add a job to the registry."""
        data = self._load()
        data["jobs"].append(job.to_dict())
        self._save(data)

    def list_jobs(self) -> list[JobHandle]:
        """List all tracked jobs."""
        data = self._load()
        return [JobHandle.from_dict(j) for j in data.get("jobs", [])]

    def get(self, job_id: str) -> JobHandle | None:
        """Get a job by its local ID."""
        for job in self.list_jobs():
            if job.job_id == job_id:
                return job
        return None

    def update_status(self, job_id: str, status: str) -> None:
        """Update the status of a job."""
        data = self._load()
        for job_data in data.get("jobs", []):
            if job_data["job_id"] == job_id:
                job_data["status"] = status
                break
        self._save(data)

    def remove(self, job_id: str) -> bool:
        """Remove a job from the registry. Returns True if found."""
        data = self._load()
        original_len = len(data.get("jobs", []))
        data["jobs"] = [j for j in data.get("jobs", []) if j["job_id"] != job_id]
        if len(data["jobs"]) < original_len:
            self._save(data)
            return True
        return False
