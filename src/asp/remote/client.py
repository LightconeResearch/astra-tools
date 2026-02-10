"""Cluster client abstraction for remote execution.

Provides a uniform interface for HPC clusters using SSH/SFTP for all operations:
file transfer, job submission (sbatch/srun), and status queries (sacct).
"""

from __future__ import annotations

import logging
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asp.helpers import load_yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RemoteEntry:
    """A file or directory entry on a remote system."""

    name: str
    path: str
    is_dir: bool
    size: int | None = None


class JobState:
    """State of a remote Slurm job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

    def __init__(self, state: str, raw: str | None = None) -> None:
        self.state = state
        self.raw = raw or state

    @property
    def is_terminal(self) -> bool:
        return self.state in (self.COMPLETED, self.FAILED, self.CANCELLED, self.TIMEOUT)

    def __repr__(self) -> str:
        return f"JobState({self.state!r})"

    def __str__(self) -> str:
        return self.state


# ---------------------------------------------------------------------------
# Abstract client + SSH backend
# ---------------------------------------------------------------------------


class ClusterClient(ABC):
    """Uniform interface for HPC clusters."""

    @abstractmethod
    def ls(self, path: str) -> list[RemoteEntry]:
        """List directory contents on the remote system."""
        ...

    @abstractmethod
    def upload(self, local_path: Path, remote_path: str) -> None:
        """Upload a local file or directory to the remote system."""
        ...

    @abstractmethod
    def download(self, remote_path: str, local_path: Path) -> Path:
        """Download a remote file or directory to a local path."""
        ...

    @abstractmethod
    def submit_batch(self, script_path: str) -> str:
        """Submit a pre-uploaded batch script and return the Slurm job ID."""
        ...

    @abstractmethod
    def run_interactive(self, script_path: str, slurm_args: list[str]) -> dict[str, str]:
        """Run a script via srun (blocks until completion). Returns stdout/stderr/returncode."""
        ...

    @abstractmethod
    def job_status(self, jobid: str) -> JobState:
        """Check the status of a Slurm job."""
        ...


class SSHBackend(ClusterClient):
    """Pure SSH/SFTP backend for HPC clusters.

    Uses paramiko for all operations: file transfer via SFTP,
    job submission via SSH exec of sbatch/srun, status via sacct.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize the SSH client connection."""
        if self._client is None:
            from asp.remote.bootstrap import _get_ssh_client

            host = self.config["ssh_host"]
            user = self.config["ssh_user"]
            key_path = self.config.get("ssh_key")
            self._client = _get_ssh_client(
                host, user, key_path=Path(key_path) if key_path else None
            )
        return self._client

    def _exec(self, command: str) -> tuple[str, str, int]:
        """Run a command over SSH using login shell."""
        from asp.remote.bootstrap import _run_ssh_command

        client = self._get_client()
        modules = self.config.get("modules", [])
        return _run_ssh_command(client, command, modules=modules if modules else None)

    def ls(self, path: str) -> list[RemoteEntry]:
        """List directory via SFTP."""
        client = self._get_client()
        sftp = client.open_sftp()
        try:
            entries = []
            for attr in sftp.listdir_attr(path):
                entries.append(RemoteEntry(
                    name=attr.filename,
                    path=f"{path}/{attr.filename}",
                    is_dir=stat.S_ISDIR(attr.st_mode) if attr.st_mode else False,
                    size=attr.st_size,
                ))
            return entries
        finally:
            sftp.close()

    def upload(self, local_path: Path, remote_path: str) -> None:
        """Upload a file or directory via SFTP."""
        client = self._get_client()
        sftp = client.open_sftp()
        try:
            if local_path.is_dir():
                _sftp_upload_dir(sftp, local_path, remote_path)
            else:
                # Ensure parent directory exists
                parent = remote_path.rsplit("/", 1)[0] if "/" in remote_path else "."
                _sftp_makedirs(sftp, parent)
                sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()

    def download(self, remote_path: str, local_path: Path) -> Path:
        """Download a file or directory via SFTP."""
        client = self._get_client()
        sftp = client.open_sftp()
        try:
            try:
                remote_stat = sftp.stat(remote_path)
            except FileNotFoundError:
                raise FileNotFoundError(f"Remote path not found: {remote_path}")

            if stat.S_ISDIR(remote_stat.st_mode) if remote_stat.st_mode else False:
                _sftp_download_dir(sftp, remote_path, local_path)
            else:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote_path, str(local_path))
            return local_path
        finally:
            sftp.close()

    def submit_batch(self, script_path: str) -> str:
        """Submit a batch script via sbatch over SSH."""
        stdout, stderr, exit_code = self._exec(f"sbatch {script_path}")
        if exit_code != 0:
            raise RuntimeError(f"sbatch failed: {stderr}")
        # sbatch output: "Submitted batch job 12345"
        return stdout.strip().split()[-1]

    def run_interactive(self, script_path: str, slurm_args: list[str]) -> dict[str, str]:
        """Run a script via srun over SSH. Blocks until completion."""
        args_str = " ".join(slurm_args)
        stdout, stderr, exit_code = self._exec(f"srun {args_str} bash {script_path}")
        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": str(exit_code),
        }

    def job_status(self, jobid: str) -> JobState:
        """Check Slurm job status via sacct over SSH."""
        stdout, _, exit_code = self._exec(
            f"sacct -j {jobid} --format=State --noheader --parsable2"
        )
        if exit_code != 0:
            return JobState(JobState.UNKNOWN, raw="sacct failed")

        lines = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
        raw = lines[0] if lines else "UNKNOWN"

        state_map = {
            "PENDING": JobState.PENDING,
            "RUNNING": JobState.RUNNING,
            "COMPLETED": JobState.COMPLETED,
            "FAILED": JobState.FAILED,
            "CANCELLED": JobState.CANCELLED,
            "TIMEOUT": JobState.TIMEOUT,
        }
        return JobState(state_map.get(raw, JobState.UNKNOWN), raw=raw)


# ---------------------------------------------------------------------------
# SFTP helpers
# ---------------------------------------------------------------------------


def _sftp_makedirs(sftp: Any, remote_path: str) -> None:
    """Recursively create directories on the remote via SFTP."""
    parts = remote_path.split("/")
    current = ""
    for part in parts:
        if not part:
            current = "/"
            continue
        current = f"{current}/{part}" if current != "/" else f"/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def _sftp_upload_dir(sftp: Any, local_dir: Path, remote_dir: str) -> None:
    """Recursively upload a local directory via SFTP."""
    _sftp_makedirs(sftp, remote_dir)
    for item in local_dir.iterdir():
        remote_path = f"{remote_dir}/{item.name}"
        if item.is_dir():
            _sftp_upload_dir(sftp, item, remote_path)
        elif item.is_file():
            sftp.put(str(item), remote_path)


def _sftp_download_dir(sftp: Any, remote_dir: str, local_dir: Path) -> None:
    """Recursively download a remote directory via SFTP."""
    local_dir.mkdir(parents=True, exist_ok=True)
    for attr in sftp.listdir_attr(remote_dir):
        remote_path = f"{remote_dir}/{attr.filename}"
        local_path = local_dir / attr.filename
        if stat.S_ISDIR(attr.st_mode) if attr.st_mode else False:
            _sftp_download_dir(sftp, remote_path, local_path)
        else:
            sftp.get(remote_path, str(local_path))


# ---------------------------------------------------------------------------
# Config loading + factory
# ---------------------------------------------------------------------------


def load_remote_config(project_dir: Path) -> dict[str, Any]:
    """Load asp-remote.yaml from the project directory.

    Args:
        project_dir: Root of the ASP project (where asp.yaml lives).

    Returns:
        The parsed remote config dict.

    Raises:
        FileNotFoundError: If asp-remote.yaml doesn't exist.
    """
    config_path = project_dir / "asp-remote.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No asp-remote.yaml found in {project_dir}")
    return load_yaml(config_path)


def get_client(project_dir: Path) -> ClusterClient:
    """Factory: reads asp-remote.yaml and returns a configured backend.

    Args:
        project_dir: Root of the ASP project (where asp.yaml lives).

    Returns:
        A configured ClusterClient instance.
    """
    config = load_remote_config(project_dir)
    target = config.get("target", "")
    clusters = config.get("clusters", {})

    if target not in clusters:
        raise ValueError(f"Target cluster '{target}' not found in asp-remote.yaml")

    cluster_config = clusters[target]
    backend = cluster_config.get("backend", "ssh")

    if backend == "ssh":
        return SSHBackend(config=cluster_config)

    if backend == "globus":
        raise ValueError(
            "The Globus backend has been removed. "
            "Update asp-remote.yaml to use 'backend: ssh' instead."
        )

    raise ValueError(f"Unknown backend: {backend}")
