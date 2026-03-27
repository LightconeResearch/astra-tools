"""ASTRA - Agentic Schema for Transparent Research Analysis.

A declarative specification format for scientific analyses.
"""

from importlib.metadata import PackageNotFoundError, version

from astra.helpers import (
    create_universe_from_defaults,
    get_analysis_decisions,
    get_decision,
    get_decisions,
    get_default_universe,
    get_finding,
    get_finding_ids,
    get_input,
    get_inputs,
    get_option,
    get_option_value,
    get_output,
    get_output_dependencies,
    get_outputs,
    get_outputs_with_recipes,
    get_prior_insight,
    get_prior_insight_ids,
    load_yaml,
    save_yaml,
)
from astra.validation import (
    get_analysis_schema,
    get_insights_schema,
    get_universe_schema,
    validate_analysis,
    validate_analysis_file,
    validate_analysis_schema,
    validate_universe,
    validate_universe_file,
    validate_universe_schema,
)

try:
    __version__ = version("astra")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = [
    # Dict-based helpers
    "create_universe_from_defaults",
    "get_analysis_decisions",
    "get_decision",
    "get_decisions",
    "get_default_universe",
    "get_finding",
    "get_finding_ids",
    "get_input",
    "get_inputs",
    "get_option",
    "get_option_value",
    "get_output",
    "get_output_dependencies",
    "get_outputs",
    "get_outputs_with_recipes",
    "get_prior_insight",
    "get_prior_insight_ids",
    "load_yaml",
    "save_yaml",
    # Validation
    "get_analysis_schema",
    "get_insights_schema",
    "get_universe_schema",
    "validate_analysis",
    "validate_analysis_file",
    "validate_analysis_schema",
    "validate_universe",
    "validate_universe_file",
    "validate_universe_schema",
    # Version
    "__version__",
]
