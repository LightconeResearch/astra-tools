"""SSH utilities for remote HPC cluster access.

Provides paramiko-based SSH/SFTP connectivity for cluster login nodes,
used by SSHBackend and CLI commands.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default sshproxy certificate location
DEFAULT_SSH_KEY = Path.home() / ".ssh" / "nersc"


class SSHCertExpiredError(Exception):
    """Raised when the SSH certificate has expired."""

    def __init__(self, expired_at: datetime, user: str | None = None) -> None:
        self.expired_at = expired_at
        now = datetime.now(timezone.utc)
        delta = now - expired_at
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 0:
            ago = f"{hours}h {minutes}m ago"
        else:
            ago = f"{minutes}m ago"
        renew_cmd = f"sshproxy -u {user}" if user else "sshproxy"
        super().__init__(
            f"NERSC SSH certificate expired {ago} (at {expired_at:%Y-%m-%d %H:%M} UTC). "
            f"Renew with: {renew_cmd}"
        )


def _check_cert_validity(cert_path: Path) -> datetime | None:
    """Check the expiry time of an OpenSSH certificate.

    Returns the expiry datetime (UTC), or None if it can't be determined.
    """
    try:
        result = subprocess.run(
            ["ssh-keygen", "-L", "-f", str(cert_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        # Look for "Valid: from YYYY-MM-DDTHH:MM:SS to YYYY-MM-DDTHH:MM:SS"
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Valid:"):
                match = re.search(r"to (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
                if match:
                    return datetime.strptime(
                        match.group(1), "%Y-%m-%dT%H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
    except Exception:
        logger.debug("Failed to check cert validity", exc_info=True)
    return None


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

    Raises:
        SSHCertExpiredError: If the SSH certificate has expired.
        FileNotFoundError: If the SSH key file doesn't exist.
    """
    try:
        import paramiko
    except ImportError:
        raise ImportError(
            "paramiko is required for SSH access. Install with: pip install paramiko"
        ) from None

    if key_path is None:
        key_path = DEFAULT_SSH_KEY

    if not key_path.exists():
        raise FileNotFoundError(
            f"SSH key not found at {key_path}. "
            f"Run 'sshproxy -u {user}' to generate a NERSC SSH certificate."
        )

    # Check cert expiry before attempting connection
    cert_path = key_path.parent / f"{key_path.name}-cert.pub"
    if cert_path.exists():
        expires = _check_cert_validity(cert_path)
        if expires is not None and datetime.now(timezone.utc) > expires:
            raise SSHCertExpiredError(expires, user=user)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=user,
            key_filename=str(key_path),
            look_for_keys=False,
        )
    except paramiko.AuthenticationException:
        # Connection failed — might be expired cert that we couldn't parse
        expires = _check_cert_validity(cert_path) if cert_path.exists() else None
        if expires is not None and datetime.now(timezone.utc) > expires:
            raise SSHCertExpiredError(expires, user=user)
        raise
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
        config: Cluster config dict from remote.yaml.

    Returns:
        True if SSH connection succeeds, False otherwise.
    """
    host = config.get("ssh_host", "")
    user = config.get("ssh_user", "")

    if not host or not user:
        return False

    key_path = config.get("ssh_key")

    try:
        client = _get_ssh_client(
            host, user, key_path=Path(key_path) if key_path else None
        )
        # Run a trivial command to verify the connection works
        stdout, _, exit_code = _run_ssh_command(client, "echo ok")
        client.close()
        return exit_code == 0 and "ok" in stdout
    except SSHCertExpiredError:
        raise  # Let callers handle this with a clear message
    except Exception:
        logger.debug("SSH check failed for %s@%s", user, host, exc_info=True)
        return False
