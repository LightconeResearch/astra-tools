"""Remote cluster execution for ASP.

Provides HPC cluster integration via SSH/SFTP for:
- Remote command execution and file transfer (``ClusterClient``, ``SSHBackend``)
- Job tracking (``JobHandle``, ``JobRegistry``)
- Batch script generation (``generate_batch_script``)
"""

from asp.remote.client import (
    ClusterClient,
    JobState,
    RemoteEntry,
    SSHBackend,
    get_client,
    load_remote_config,
)
from asp.remote.jobs import JobHandle, JobRegistry
from asp.remote.script_gen import generate_batch_script

__all__ = [
    "ClusterClient",
    "SSHBackend",
    "JobState",
    "RemoteEntry",
    "get_client",
    "load_remote_config",
    "JobHandle",
    "JobRegistry",
    "generate_batch_script",
]
