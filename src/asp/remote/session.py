"""High-level remote session wrapping ClusterClient + JobRegistry.

Provides project-aware operations: push files, pull results, exec commands,
submit jobs, and poll job status.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from asp.remote.client import ClusterClient, get_client, load_remote_config
from asp.remote.jobs import JobHandle, JobRegistry

logger = logging.getLogger(__name__)

# Directories/patterns to push by default
DEFAULT_PUSH_DIRS = ("universes", "steps", "workflows")
DEFAULT_PUSH_FILES = ("asp.yaml", "remote.yaml")

# Patterns to exclude from push
EXCLUDE_PATTERNS = (
    "results", ".asp", ".git", "__pycache__", "node_modules", ".venv", ".env",
)


class RemoteSession:
    """Project-aware wrapper around SSH client and job registry.

    Supports use as a context manager::

        with RemoteSession(project_dir) as session:
            session.push_project()
            session.exec("python run.py")

    Args:
        project_dir: Local ASP project root (where asp.yaml lives).
    """

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir.resolve()
        self._config: dict[str, Any] | None = None
        self._client: ClusterClient | None = None
        self._registry: JobRegistry | None = None

    def __enter__(self) -> "RemoteSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- Lazy properties -------------------------------------------------------

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            self._config = load_remote_config(self._project_dir)
        return self._config

    @property
    def target(self) -> str:
        return self.config.get("target", "")

    @property
    def cluster_config(self) -> dict[str, Any]:
        return self.config.get("clusters", {}).get(self.target, {})

    @property
    def client(self) -> ClusterClient:
        if self._client is None:
            self._client = get_client(self._project_dir)
        return self._client

    @property
    def registry(self) -> JobRegistry:
        if self._registry is None:
            self._registry = JobRegistry(self._project_dir)
        return self._registry

    @property
    def remote_workdir(self) -> str:
        return self.cluster_config.get("workdir", "")

    # -- Operations ------------------------------------------------------------

    def push_project(self, paths: list[str] | None = None) -> list[str]:
        """Push local project files to the remote workdir.

        Args:
            paths: Specific relative paths to push. If None, pushes the
                   default set (asp.yaml, universes/, steps/, workflows/).

        Returns:
            List of items pushed (relative paths).
        """
        workdir = self.remote_workdir
        if not workdir:
            raise ValueError("No workdir configured in remote.yaml")

        pushed: list[str] = []

        if paths is not None:
            for rel in paths:
                local = self._project_dir / rel
                if not local.exists():
                    logger.warning("Skipping non-existent path: %s", rel)
                    continue
                remote = f"{workdir}/{rel}"
                self.client.upload(local, remote)
                pushed.append(rel)
            return pushed

        # Default push: specific files + directories
        for fname in DEFAULT_PUSH_FILES:
            local = self._project_dir / fname
            if local.is_file():
                self.client.upload(local, f"{workdir}/{fname}")
                pushed.append(fname)

        for dname in DEFAULT_PUSH_DIRS:
            local = self._project_dir / dname
            if local.is_dir():
                self.client.upload(local, f"{workdir}/{dname}")
                pushed.append(f"{dname}/")

        return pushed

    def pull_results(
        self,
        universe_id: str | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Pull results from the remote cluster to local results/.

        Args:
            universe_id: Download results for this universe.
            job_id: Look up the job in the registry for workdir + universe_id.

        Returns:
            Local path where results were downloaded.
        """
        workdir = self.remote_workdir

        if job_id:
            job = self.registry.get(job_id)
            if job is None:
                raise ValueError(f"Job {job_id} not found in registry")
            universe_id = job.universe_id
            workdir = job.workdir or workdir

        if not universe_id:
            universe_id = "default"

        remote_source = f"{workdir}/results/{universe_id}"
        local_dest = self._project_dir / "results" / universe_id
        local_dest.mkdir(parents=True, exist_ok=True)

        self.client.download(remote_source, local_dest)
        return local_dest

    def exec(self, command: str, cwd: str | None = None) -> tuple[str, str, int]:
        """Run a command on the remote cluster.

        Args:
            command: Shell command to execute.
            cwd: Remote working directory (defaults to remote_workdir).

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        target_dir = cwd or self.remote_workdir
        if target_dir:
            full_command = f"cd {target_dir} && {command}"
        else:
            full_command = command
        return self.client.exec_command(full_command)

    def submit(
        self,
        script_content: str | None = None,
        universe_id: str = "default",
    ) -> JobHandle:
        """Push project, write batch script, and submit via sbatch.

        Args:
            script_content: Batch script content. If None, uses default job.sh.
            universe_id: Universe to track the job under.

        Returns:
            JobHandle for tracking.
        """
        workdir = self.remote_workdir
        if not workdir:
            raise ValueError("No workdir configured in remote.yaml")

        # Push project files first
        self.push_project()

        # Write script to remote
        script_remote = f"{workdir}/job.sh"
        if script_content:
            self.client.write_text(script_remote, script_content)
            self.client.exec_command(f"chmod +x {script_remote}")

        # Submit
        remote_job_id = self.client.submit_batch(script_remote)

        # Track
        handle = JobHandle.create(
            cluster=self.target,
            universe_id=universe_id,
            remote_job_id=remote_job_id,
            workdir=workdir,
        )
        self.registry.add(handle)
        return handle

    def poll_jobs(self) -> list[tuple[JobHandle, str, str]]:
        """Check status of all non-terminal jobs.

        Returns:
            List of (job, old_status, new_status) for jobs whose status changed.
        """
        changes: list[tuple[JobHandle, str, str]] = []

        for job in self.registry.list_jobs():
            if job.status in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"):
                continue

            try:
                state = self.client.job_status(job.remote_job_id)
            except Exception:
                logger.debug("Failed to poll job %s", job.job_id, exc_info=True)
                continue

            new_status = str(state)
            if new_status != job.status:
                old_status = job.status
                self.registry.update_status(job.job_id, new_status)
                job.status = new_status
                changes.append((job, old_status, new_status))

        return changes

    def close(self) -> None:
        """Close the underlying cluster connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
