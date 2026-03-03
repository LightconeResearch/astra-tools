"""Pydantic models for ASTRA specifications.

These models are used for schema generation and are NOT installed as part
of the astra package. They are only used by tools/generate_schemas.py.
"""

from models.analysis import Analysis, Checksum, Decision, Input, Option, Output
from models.insight import (
    Evidence,
    FigureSelector,
    FragmentSelector,
    Insight,
    InsightCollection,
    TableSelector,
    TextQuoteSelector,
)
from models.universe import Universe, UniverseNode

__all__ = [
    # Analysis
    "Analysis",
    "Checksum",
    "Decision",
    "Input",
    "Option",
    "Output",
    # Universe
    "Universe",
    "UniverseNode",
    # Insight - W3C Selectors
    "TextQuoteSelector",
    "FragmentSelector",
    "FigureSelector",
    "TableSelector",
    # Insight - Core
    "Evidence",
    "Insight",
    "InsightCollection",
]
