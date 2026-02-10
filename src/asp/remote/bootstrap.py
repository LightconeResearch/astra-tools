"""SSH utilities for remote HPC cluster access.

Provides paramiko-based SSH/SFTP connectivity for cluster login nodes,
used by SSHBackend and CLI commands.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default sshproxy certificate location
DEFAULT_SSH_KEY = Path.home() / ".ssh" / "nersc"


def _get_ssh_client(
    host: str,
    user: str,
    key_path: Path | None = None,
) -> Any:
    """Create a paramiko SSH client connected to the host.

    Args:
        host: SSH hostname.
        user: SSH username.
        key_path: Path to private key (default: ~/.ssh/nersc from sshproxy).

    Returns:
        Connected paramiko.SSHClient.
    """
    try:
        import paramiko
    except ImportError:
        raise ImportError(
            "paramiko is required for SSH access. Install with: pip install asp[remote]"
        ) from None

    if key_path is None:
        key_path = DEFAULT_SSH_KEY

    if not key_path.exists():
        raise FileNotFoundError(
            f"SSH key not found at {key_path}. "
            "Run 'sshproxy' to generate a NERSC SSH certificate."
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        username=user,
        key_filename=str(key_path),
        look_for_keys=False,
    )
    return client


def _run_ssh_command(
    client: Any, command: str, modules: list[str] | None = None
) -> tuple[str, str, int]:
    """Run a command over SSH as a login shell.

    Uses ``bash -l -c`` to ensure the full login environment is available
    (module system, ~/.local/bin on PATH, etc.).

    Args:
        client: Connected paramiko SSHClient.
        command: Shell command to run.
        modules: Optional list of modules to load before running.
    """
    if modules:
        module_cmds = "; ".join(f"module load {m} 2>/dev/null" for m in modules)
        # After loading modules, add Python user-scripts dir to PATH
        # (pip install --user puts binaries there, e.g. ~/.local/.../bin)
        add_user_bin = (
            'export PATH="$(python3 -m site --user-base 2>/dev/null)/bin:$PATH"'
        )
        command = f"{module_cmds}; {add_user_bin}; {command}"
    # Wrap in login shell for proper environment
    wrapped = f"bash -l -c {shlex.quote(command)}"
    _, stdout, stderr = client.exec_command(wrapped)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_code


def _run_ssh_raw(client: Any, command: str) -> tuple[str, str, int]:
    """Run a raw command over SSH without login shell wrapping.

    Used for commands like heredocs that don't work well inside bash -l -c.
    """
    _, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_code


def check_ssh(config: dict[str, Any]) -> bool:
    """Check SSH connectivity to the cluster.

    Args:
        config: Cluster config dict from asp-remote.yaml.

    Returns:
        True if SSH connection succeeds, False otherwise.
    """
    host = config.get("ssh_host", "")
    user = config.get("ssh_user", "")

    if not host or not user:
        return False

    try:
        client = _get_ssh_client(host, user)
        # Run a trivial command to verify the connection works
        stdout, _, exit_code = _run_ssh_command(client, "echo ok")
        client.close()
        return exit_code == 0 and "ok" in stdout
    except Exception:
        logger.debug("SSH check failed for %s@%s", user, host, exc_info=True)
        return False
