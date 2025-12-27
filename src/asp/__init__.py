"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.
"""

from asp.models.analysis import Analysis, Decision, Input, Option, Output
from asp.models.universe import Universe

try:
    from asp._version import __version__, __version_tuple__
except ImportError:
    # Package not installed, fallback for development
    __version__ = "0.0.0.dev0"
    __version_tuple__ = (0, 0, 0, "dev0")

__all__ = [
    "Analysis",
    "Decision",
    "Input",
    "Option",
    "Output",
    "Universe",
    "__version__",
    "__version_tuple__",
]
