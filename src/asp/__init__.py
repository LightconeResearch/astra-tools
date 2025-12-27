"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.
"""

__version__ = "0.1.0"

from asp.models.analysis import Analysis, Decision, Input, Option, Output
from asp.models.universe import Universe

__all__ = [
    "Analysis",
    "Decision",
    "Input",
    "Option",
    "Output",
    "Universe",
    "__version__",
]
