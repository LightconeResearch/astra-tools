"""Pydantic models for scientific insights.

Insight model with W3C Web Annotation-compliant selectors for referencing
content in scientific papers AND analysis-generated artifacts.

Evidence can come from two sources:
- **Literature**: Referenced by DOI with W3C selectors into PDFs
- **Analysis artifacts**: Referenced by output ID (string)

W3C Web Annotation compliance:
- TextQuoteSelector: https://www.w3.org/TR/annotation-model/#text-quote-selector
- FragmentSelector: https://www.w3.org/TR/annotation-model/#fragment-selector
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# =============================================================================
# W3C Web Annotation Selectors
# =============================================================================


class TextQuoteSelector(BaseModel):
    """W3C TextQuoteSelector for locating text in a document.

    See: https://www.w3.org/TR/annotation-model/#text-quote-selector

    The authoritative anchor for verification. Text should be normalized
    (HTML/XML tags removed, entities decoded).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["TextQuoteSelector"] = "TextQuoteSelector"
    exact: str = Field(min_length=1, description="Exact quoted text (1-3 sentences)")
    prefix: str | None = Field(default=None, description="~20-100 chars before for disambiguation")
    suffix: str | None = Field(default=None, description="~20-100 chars after for disambiguation")


class FragmentSelector(BaseModel):
    """W3C FragmentSelector for PDF locations.

    See: https://www.w3.org/TR/annotation-model/#fragment-selector
    Conforms to RFC 3778/8118 for PDF fragments.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["FragmentSelector"] = "FragmentSelector"
    conforms_to: Literal["http://tools.ietf.org/rfc/rfc3778"] = Field(
        default="http://tools.ietf.org/rfc/rfc3778",
        alias="conformsTo",
    )
    value: str | None = Field(default=None, description="Fragment (e.g., 'page=6')")
    page: int | None = Field(default=None, ge=1, description="1-indexed page number")


class FigureSelector(BaseModel):
    """Selector for referencing figures in scientific papers.

    Extension of W3C selector pattern for scientific literature.
    The label is the authoritative identifier (e.g., "Figure 3a").
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["FigureSelector"] = "FigureSelector"
    label: str = Field(min_length=1, description="Figure label (e.g., 'Figure 3a', 'Fig. 1')")
    caption: str | None = Field(default=None, description="Caption text for verification")


class TableSelector(BaseModel):
    """Selector for referencing tables in scientific papers.

    Extension of W3C selector pattern for scientific literature.
    The label is the authoritative identifier (e.g., "Table 2").
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["TableSelector"] = "TableSelector"
    label: str = Field(min_length=1, description="Table label (e.g., 'Table 1', 'Tab. 2')")
    caption: str | None = Field(default=None, description="Caption/header text for verification")
    region: str | None = Field(default=None, description="Specific region (e.g., 'row 3')")


# =============================================================================
# Evidence
# =============================================================================


class Evidence(BaseModel):
    """Evidence from a source with W3C-compliant selectors.

    Evidence can reference two kinds of sources:

    - **Literature** (``doi``): A paper referenced by DOI, with W3C selectors
      pointing into the PDF. For arXiv papers, use DOI format
      ``10.48550/arXiv.{id}`` and set ``version``.

    - **Analysis artifact** (``artifact``): An output produced by this
      analysis, referenced by its output ID (the ``id`` field in
      ``outputs``). The optional ``checksum`` ensures artifact integrity.

    Exactly one of ``doi`` or ``artifact`` must be set.
    At least one content selector (quote, figure, or table) is required.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["doi"],
                    "properties": {"doi": {"type": "string"}},
                },
                {
                    "required": ["artifact"],
                    "properties": {
                        "artifact": {"type": "string"},
                    },
                },
            ]
        },
    )

    id: str = Field(min_length=1, description="Evidence ID")

    # Source: exactly one of doi or artifact
    doi: str | None = Field(
        default=None,
        pattern=r"^10\.\d{4,}/.*$",
        description="DOI of the source paper (e.g., '10.48550/arXiv.1706.03762')",
    )
    artifact: str | None = Field(
        default=None,
        description="Output ID referencing a declared output in this analysis",
    )

    # Literature-specific
    version: int | None = Field(
        default=None,
        ge=1,
        description="Paper version for arXiv papers (version matters for reproducibility)",
    )

    # Artifact-specific
    checksum: Checksum | None = Field(
        default=None,
        description="Checksum of the artifact for integrity verification",
    )

    # Artifact snapshot (immutable copy for iterative analysis)
    snapshot: str | None = Field(
        default=None,
        description="Path to immutable copy of the artifact (only valid when artifact is set)",
    )
    source_commit: str | None = Field(
        default=None,
        description="Git commit that produced the original artifact "
        "(only valid when artifact is set)",
    )

    # Content selectors (at least one required)
    quote: TextQuoteSelector | None = Field(default=None, description="Text quote anchor")
    figure: FigureSelector | None = Field(default=None, description="Figure reference")
    table: TableSelector | None = Field(default=None, description="Table reference")

    # Location hint
    location: FragmentSelector | None = Field(
        default=None, description="Location hint (page number for PDFs/reports)"
    )

    @model_validator(mode="after")
    def validate_source(self) -> Evidence:
        """Ensure exactly one source type and at least one content selector."""
        has_doi = self.doi is not None
        has_artifact = self.artifact is not None

        if has_doi == has_artifact:
            raise ValueError("Evidence must have exactly one of 'doi' (literature) or 'artifact'")

        if has_doi and self.checksum is not None:
            raise ValueError("'checksum' is only valid for artifact evidence, not literature")

        if has_doi and self.snapshot is not None:
            raise ValueError("'snapshot' is only valid for artifact evidence, not literature")

        if has_doi and self.source_commit is not None:
            raise ValueError("'source_commit' is only valid for artifact evidence, not literature")

        if has_artifact and self.version is not None:
            raise ValueError("'version' is only valid for literature evidence, not artifacts")

        if has_doi and not (self.quote or self.figure or self.table):
            raise ValueError(
                "Literature evidence must have at least one content selector: "
                "quote, figure, or table"
            )
        return self

    @property
    def is_literature(self) -> bool:
        """Check if this evidence references a paper."""
        return self.doi is not None

    @property
    def is_artifact(self) -> bool:
        """Check if this evidence references an analysis artifact."""
        return self.artifact is not None

    @property
    def is_arxiv(self) -> bool:
        """Check if this evidence references an arXiv paper."""
        return self.doi is not None and self.doi.startswith("10.48550/arXiv.")

    @property
    def arxiv_id(self) -> str | None:
        """Extract arXiv ID from DOI if this is an arXiv paper."""
        if self.is_arxiv:
            assert self.doi is not None
            return self.doi.replace("10.48550/arXiv.", "")
        return None


# =============================================================================
# Insight
# =============================================================================


class Insight(BaseModel):
    """A unit of scientific knowledge backed by evidence.

    Used for both ``prior_insights`` (informing decisions) and ``findings``
    (conclusions from the analysis) on an analysis node. The placement
    determines direction; the model is the same in both cases.

    Evidence can reference literature (by DOI) or analysis output artifacts
    (by output ID via ``Evidence.artifact``). At least one evidence item
    is required.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Required
    id: str = Field(min_length=1, description="Unique identifier")
    claim: str = Field(min_length=1, description="What we learned (1-2 sentences)")
    created_at: datetime = Field(description="Creation timestamp (ISO 8601)")

    # Evidence supporting this insight
    evidence: list[Evidence] = Field(
        min_length=1, description="Supporting evidence (papers or analysis artifacts)"
    )

    # Optional classification
    derived: bool = Field(default=False, description="True if synthesized/inferred")

    # Optional context
    scope: str | None = Field(default=None, description="Applicability conditions")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    notes: str | None = Field(default=None, description="Reasoning notes")


# =============================================================================
# Collection
# =============================================================================


class InsightCollection(BaseModel):
    """Collection of insights, usable standalone or embedded in an analysis."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://astra-spec.org/v1/insights.schema.json",
            "title": "ASTRA Insights Collection",
        },
    )

    schema_: str | None = Field(default=None, alias="$schema")
    insights: dict[str, Insight] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> InsightCollection:
        """Load from YAML file."""
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))

    def to_yaml(self, path: str | Path) -> None:
        """Save to YAML file."""
        with open(path, "w") as f:
            yaml.safe_dump(
                self.model_dump(by_alias=True, exclude_none=True, mode="json"),
                f,
                sort_keys=False,
                allow_unicode=True,
            )

    def get_insight(self, insight_id: str) -> Insight | None:
        """Get insight by ID."""
        return self.insights.get(insight_id)


# Resolve forward references to Checksum from models.analysis.
# Imported here (at module bottom) to avoid circular imports at module load time.
from models.analysis import Checksum  # noqa: E402

Evidence.model_rebuild()
Insight.model_rebuild()
InsightCollection.model_rebuild()
