"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.
"""

from importlib.metadata import PackageNotFoundError, version

from asp.helpers import (
    create_universe_from_defaults,
    get_decision,
    get_decisions,
    get_default_universe,
    get_input,
    get_inputs,
    get_option,
    get_option_value,
    get_output,
    get_outputs,
    load_yaml,
    save_yaml,
)
from asp.validation import (
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
    __version__ = version("asp")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = [
    # Dict-based helpers
    "create_universe_from_defaults",
    "get_decision",
    "get_decisions",
    "get_default_universe",
    "get_input",
    "get_inputs",
    "get_option",
    "get_option_value",
    "get_output",
    "get_outputs",
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
