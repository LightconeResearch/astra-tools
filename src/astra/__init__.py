"""ASTRA - Agentic Schema for Transparent Research Analysis.

A declarative specification format for scientific analyses,
with a LinkML schema as the single source of truth.
"""

from importlib.metadata import PackageNotFoundError, version

from astra.export import export_rocrate
from astra.helpers import (
    generate_default_universe,
    get_decision,
    get_decisions,
    get_input,
    get_option,
    get_output,
    get_output_dependencies,
    get_sub_analysis,
    get_universe,
    get_universe_selections,
    is_condition_met,
    walk_decisions,
)
from astra.loader import find_analysis_dir, load_analysis, load_yaml, save_yaml, validate_yaml

try:
    __version__ = version("astra")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = [
    # Loading
    "load_yaml",
    "load_analysis",
    "save_yaml",
    "validate_yaml",
    "find_analysis_dir",
    # Helpers
    "get_input",
    "get_output",
    "get_decision",
    "get_decisions",
    "get_option",
    "get_universe",
    "get_universe_selections",
    "get_sub_analysis",
    "get_output_dependencies",
    "generate_default_universe",
    "is_condition_met",
    "walk_decisions",
    # Export
    "export_rocrate",
    # Version
    "__version__",
]
