"""Pydantic models for ASTRA analysis specifications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Checksum(BaseModel):
    """Checksum for data integrity verification."""

    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["sha256", "sha512", "md5"] = Field(description="Hash algorithm")
    value: str = Field(description="Hash value")


class Input(BaseModel):
    """An input to the analysis.

    Two kinds of inputs:
    - ``type: data`` — a dataset, file, or external resource (specify ``source``)
    - ``type: analysis`` — outputs from another ASTRA analysis (specify ``ref``)

    Sub-analysis inputs can also use ``from`` to reference a parent input
    or a sibling's output (e.g., ``from: sibling_id.output_id``).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Unique identifier for the input",
    )
    type: Literal["data", "analysis"] = Field(description="Type of input")
    description: str | None = Field(default=None, description="Description of the input")

    # Data inputs
    source: str | None = Field(
        default=None, description="URI or path to the data source"
    )
    checksum: Checksum | None = Field(
        default=None, description="Checksum for data integrity verification"
    )

    # Analysis inputs
    ref: str | None = Field(
        default=None, description="Reference to another ASTRA analysis"
    )
    ref_version: str | None = Field(
        default=None, description="Version of the referenced analysis"
    )
    use_outputs: list[str] | None = Field(
        default=None, description="Specific outputs to use from referenced analysis"
    )

    # Sub-analysis wiring
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Reference to parent input or sibling output "
        "(e.g., 'input_id' or 'sibling.output_id')",
    )


class Resources(BaseModel):
    """Compute resource requirements for a recipe."""

    model_config = ConfigDict(extra="forbid")

    cpus: int | None = Field(default=None, ge=1, description="Number of CPUs")
    memory: str | None = Field(
        default=None, description="Memory requirement (e.g., '8GB', '512MB')"
    )
    gpus: int | None = Field(default=None, ge=1, description="Number of GPUs")
    time_limit: str | None = Field(
        default=None, description="Maximum wall time (e.g., '2h', '30m')"
    )


class ContainerBuildSpec(BaseModel):
    """Specification for building a container image from a Containerfile."""

    model_config = ConfigDict(extra="forbid")

    build: str = Field(description="Path to Containerfile relative to project root")
    context: str | None = Field(default=None, description="Build context directory")
    args: dict[str, str] | None = Field(default=None, description="Docker build arguments")


class Recipe(BaseModel):
    """A build rule that produces an output.

    Recipes are the execution contract: run this command (optionally in a
    container) to produce the parent output. Dependencies on other outputs
    are declared via ``inputs``.
    """

    model_config = ConfigDict(extra="forbid")

    command: str = Field(description="Command to execute (e.g., 'python src/train.py')")
    inputs: list[str] | None = Field(
        default=None,
        description="Output IDs that must be materialized before this recipe runs",
    )
    container: str | ContainerBuildSpec | None = Field(
        default=None,
        description="Container image override (defaults to node-level container). "
        "Can be a string (pre-built image) or a build spec with 'build' key.",
    )
    resources: Resources | None = Field(
        default=None,
        description="Compute resource requirements",
    )


class Output(BaseModel):
    """An expected output from the analysis.

    Outputs can declare their provenance via ``from`` to trace which
    sub-analysis produces them (e.g., ``from: inference.posterior``).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Unique identifier for the output",
    )
    type: Literal["metric", "figure", "table", "data", "report"] = Field(
        description="Type of output"
    )
    description: str | None = Field(default=None, description="Description of the output")

    # Provenance: which sub-analysis produces this output
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Sub-analysis output that produces this "
        "(e.g., 'sub_analysis.output_id')",
    )

    # Execution: how to produce this output
    recipe: Recipe | None = Field(
        default=None,
        description="Inline recipe describing how to produce this output",
    )


class Option(BaseModel):
    """An option for a decision."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Human-readable name for the option")
    description: str | None = Field(default=None, description="Detailed description of the option")
    insights: list[str] | None = Field(
        default=None, description="List of insight IDs supporting this option"
    )
    incompatible_with: list[str] | None = Field(
        default=None,
        description="List of decision.option pairs that cannot be selected together",
    )
    requires: list[str] | None = Field(
        default=None,
        description="List of decision.option pairs that must also be selected",
    )
    excluded: bool = Field(default=False, description="Whether this option was considered and rejected")
    excluded_reason: str | None = Field(
        default=None, description="Why this option was excluded"
    )


class Decision(BaseModel):
    """A decision point in the analysis."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Human-readable name for the decision")
    rationale: str | None = Field(default=None, description="Why this decision exists")
    tags: list[str] | None = Field(
        default=None, description="Tags for grouping and categorizing this decision"
    )
    when: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        description="Condition: 'decision_id.option_id' — this decision only exists when that option is selected",
    )
    default: str | None = Field(
        default=None, description="Default option ID for baseline universes"
    )
    options: dict[str, Option] = Field(description="Map of option IDs to option specifications")

    @model_validator(mode="after")
    def validate_default_exists(self) -> Decision:
        """Ensure default option exists in options."""
        if self.default is not None and self.default not in self.options:
            raise ValueError(f"Default option '{self.default}' not found in options")
        return self


class SuccessCriterion(BaseModel):
    """A structured criterion linking a claim to an output and condition."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="Human-readable statement of the criterion")
    output: str | None = Field(
        default=None,
        description="ID of the output to check against",
    )
    condition: str | None = Field(
        default=None,
        description="Condition to evaluate, e.g. 'value > 0.95'",
    )

    @model_validator(mode="after")
    def validate_condition_requires_output(self) -> SuccessCriterion:
        """Ensure condition is only set when output is also set."""
        if self.condition is not None and self.output is None:
            raise ValueError("'condition' requires 'output' to be set")
        return self


class Analysis(BaseModel):
    """A self-similar analysis specification.

    Every level has the same structure: metadata, inputs, outputs,
    decisions, insights, and optional sub-analyses. A sub-analysis extracted
    to its own file is a valid Analysis on its own.

    At the root level, ``version``, ``name``, ``inputs``, and
    ``outputs`` are required. In sub-analyses they are optional.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://astra-spec.org/v1/analysis.schema.json",
            "title": "ASTRA Analysis Specification",
        },
    )

    # Document metadata
    schema_: str | None = Field(default=None, alias="$schema", description="JSON Schema reference")
    version: str | None = Field(
        default=None,
        pattern=r"^\d+\.\d+(\.\d+)?$",
        description="ASTRA specification version",
    )

    # Analysis identity
    name: str | None = Field(default=None, description="Human-readable name for the analysis")
    authors: list[str] | None = Field(default=None, description="List of authors")
    tags: list[str] | None = Field(default=None, description="Tags for categorization")

    # Analysis content
    description: str | None = Field(
        default=None, description="Detailed description of this analysis"
    )
    success_criteria: list[SuccessCriterion] | None = Field(
        default=None,
        description="Concrete criteria for determining if this analysis succeeded. "
        "Each criterion is a structured object with a claim and optional output reference.",
    )
    inputs: list[Input] | None = Field(
        default=None,
        description="List of inputs for this analysis",
    )
    outputs: list[Output] | None = Field(
        default=None,
        description="List of expected outputs from this analysis",
    )
    decisions: dict[str, Decision] = Field(
        default_factory=dict,
        description="Map of decision IDs to decision specifications",
    )
    insights: dict[str, Insight] = Field(
        default_factory=dict,
        description="Map of insight IDs to insight specifications",
    )

    # Execution
    container: str | ContainerBuildSpec | None = Field(
        default=None,
        description="Default container image for recipes in this node. "
        "Can be a string (pre-built image) or a build spec with 'build' key.",
    )
    # Self-similar nesting
    analyses: dict[str, Analysis] | None = Field(
        default=None,
        description="Map of sub-analysis IDs to nested analyses",
    )



# Resolve forward references to Insight from models.insight.
# Imported here (at module bottom) to avoid circular imports at module load time.
from models.insight import Insight  # noqa: E402

Analysis.model_rebuild()
