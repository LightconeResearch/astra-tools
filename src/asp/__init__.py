"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.
"""

from importlib.metadata import version

from asp.models.analysis import Analysis, Decision, Input, Option, Output
from asp.models.universe import Universe

__version__ = version("asp")

__all__ = [
    "Analysis",
    "Decision",
    "Input",
    "Option",
    "Output",
    "Universe",
    "__version__",
]
