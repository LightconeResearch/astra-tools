"""ASTRA - Agentic Schema for Transparent Research Analysis.

A declarative specification format for scientific analyses,
implemented as an RO-Crate Profile.
"""

from importlib.metadata import PackageNotFoundError, version

from astra.crate import ASTRACrate

try:
    __version__ = version("astra")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = [
    "ASTRACrate",
    "__version__",
]
