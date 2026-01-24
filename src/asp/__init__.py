"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.
"""

from importlib.metadata import version

from asp.helpers import (
    create_universe_from_defaults,
    get_decision,
    get_default_universe,
    get_input,
    get_output,
    load_yaml,
    save_yaml,
)
from asp.models.analysis import Analysis, Decision, Input, Option, Output
from asp.models.universe import Universe
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

__version__ = version("asp")

__all__ = [
    # Pydantic Models (for convenience and workflow module)
    "Analysis",
    "Decision",
    "Input",
    "Option",
    "Output",
    "Universe",
    # Dict-based helpers
    "create_universe_from_defaults",
    "get_decision",
    "get_default_universe",
    "get_input",
    "get_output",
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
