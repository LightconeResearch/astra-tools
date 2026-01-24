"""Pydantic models for scientific insights."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaperSource(BaseModel):
    """Source reference to a scientific paper."""

    model_config = ConfigDict(extra="forbid")

    doi: str = Field(
        pattern=r"^10\.\d{4,}/.*$",
        description="DOI of the paper (e.g., '10.1038/s41586-023-06221-2')",
    )


class AnalysisSource(BaseModel):
    """Source reference to a previous ASP analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(description="Reference to the analysis (e.g., 'org/analysis-name')")
    version: str | None = Field(default=None, description="Version of the analysis")
    universe: str | None = Field(default=None, description="Specific universe used")


class FigureEvidence(BaseModel):
    """Evidence from a figure."""

    model_config = ConfigDict(extra="forbid")

    figure: str = Field(description="Figure reference (e.g., 'Figure 3a')")
    caption: str | None = Field(default=None, description="Figure caption or description")


class QuoteEvidence(BaseModel):
    """Evidence from a direct quote."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(description="The exact quoted text")
    location: str | None = Field(
        default=None, description="Location in source (e.g., 'Section 2.1, p.3')"
    )


class TableEvidence(BaseModel):
    """Evidence from a table."""

    model_config = ConfigDict(extra="forbid")

    table: str = Field(description="Table reference (e.g., 'Table 1')")
    location: str | None = Field(default=None, description="Specific row/column if applicable")
    value: str | None = Field(default=None, description="The specific value referenced")


class EquationEvidence(BaseModel):
    """Evidence from an equation."""

    model_config = ConfigDict(extra="forbid")

    equation: str = Field(description="Equation reference (e.g., 'Equation 7')")
    expression: str | None = Field(default=None, description="The mathematical expression")


class ResultEvidence(BaseModel):
    """Evidence from a numerical result."""

    model_config = ConfigDict(extra="forbid")

    result: str = Field(description="Description of the result")
    location: str | None = Field(default=None, description="Where in the source")
    value: Any | None = Field(default=None, description="The numerical value")


class MetricEvidence(BaseModel):
    """Evidence from an analysis metric output."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(description="Name of the metric")
    value: Any = Field(description="The metric value(s)")


class OutputEvidence(BaseModel):
    """Evidence from an analysis output artifact."""

    model_config = ConfigDict(extra="forbid")

    output: str = Field(description="Output ID or path")


# Union type for all evidence types
InsightEvidence = (
    FigureEvidence
    | QuoteEvidence
    | TableEvidence
    | EquationEvidence
    | ResultEvidence
    | MetricEvidence
    | OutputEvidence
)


class Insight(BaseModel):
    """A scientific insight with provenance and supporting evidence.

    An insight is a discrete unit of scientific knowledge that can come from
    either literature (papers) or computation (previous analyses).
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="The insight content - what we learned (1-2 sentences)")
    source: PaperSource | AnalysisSource = Field(
        description="Where this insight comes from (paper DOI or analysis reference)"
    )
    evidence: list[InsightEvidence] = Field(
        default_factory=list,
        description="Supporting evidence for this insight (figures, quotes, tables, etc.)",
    )
    scope: str | None = Field(
        default=None,
        description="Context or conditions where this insight applies",
    )

    @model_validator(mode="after")
    def validate_evidence_types(self) -> Insight:
        """Validate that evidence types match the source type."""
        is_paper = isinstance(self.source, PaperSource)

        for ev in self.evidence:
            # Analysis-specific evidence types
            analysis_types = (MetricEvidence, OutputEvidence)

            if is_paper and isinstance(ev, analysis_types):
                raise ValueError(
                    f"Evidence type '{type(ev).__name__}' is not valid for paper sources. "
                    "Use figure, quote, table, equation, or result evidence."
                )

        return self


class InsightCollection(BaseModel):
    """A collection of scientific insights.

    Can be used as a standalone file or embedded in an analysis.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://asp-spec.org/v1/insights.schema.json",
            "title": "ASP Insights Collection",
        },
    )

    schema_: str | None = Field(default=None, alias="$schema", description="JSON Schema reference")
    insights: dict[str, Insight] = Field(
        default_factory=dict,
        description="Map of insight IDs to insight specifications",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> InsightCollection:
        """Load insights from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save insights to a YAML file."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    def get_insight(self, insight_id: str) -> Insight | None:
        """Get an insight by ID."""
        return self.insights.get(insight_id)
