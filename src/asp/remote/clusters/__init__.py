"""Cluster registry — discovers supported clusters from subdirectories.

Each cluster is a subdirectory containing:
  config.yaml  — cluster configuration (required)
  README.md    — cluster-specific setup guide (optional)

To add a new cluster, create a new subdirectory with a config.yaml.
See perlmutter/ for the expected format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from asp.helpers import load_yaml

_CLUSTERS_DIR = Path(__file__).parent


def load_cluster_registry() -> dict[str, dict[str, Any]]:
    """Load all cluster definitions from subdirectories.

    Returns:
        Dict mapping cluster name to its config dict.
    """
    registry: dict[str, dict[str, Any]] = {}
    for config_file in sorted(_CLUSTERS_DIR.glob("*/config.yaml")):
        cluster_id = config_file.parent.name
        spec = load_yaml(config_file)
        # Expand ~ in ssh_key path
        if "ssh_key" in spec:
            spec["ssh_key"] = str(Path(spec["ssh_key"]).expanduser())
        registry[cluster_id] = spec
    return registry
