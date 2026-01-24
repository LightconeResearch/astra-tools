"""ASP - Agentic Science Protocol.

A declarative specification format for scientific analyses.

The asp package provides CLI tools and validation against JSON schemas.
It does NOT interact with Pydantic models - only with JSON schema files.

For programmatic access to Pydantic models, import from 'models' directly:
    from models import Analysis, Universe
"""

from importlib.metadata import version

__version__ = version("asp")

__all__ = [
    "__version__",
]
