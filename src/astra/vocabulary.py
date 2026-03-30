"""ASTRA vocabulary constants and JSON-LD context.

Defines the ASTRA RO-Crate Profile vocabulary: types, properties, and the
JSON-LD context for embedding in ro-crate-metadata.json files.

Design principle: reuse schema.org, Bioschemas, Web Annotation (oa:), and
Workflow Run Crate (wfrun:) vocabulary wherever possible. Custom ASTRA terms
are only introduced for genuinely novel multiverse-analysis concepts.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

ASTRA_NS = "https://w3id.org/astra/terms/"
ASTRA_CONTEXT_URL = "https://w3id.org/astra/context"
ASTRA_PROFILE_URL = "https://w3id.org/astra/profile/1.0"
ROCRATE_PROFILE = "https://w3id.org/ro/crate/1.2"
ROCRATE_CONTEXT_URL = f"{ROCRATE_PROFILE}/context"
WFRUN_NS = "https://w3id.org/ro/terms/workflow-run#"

# ---------------------------------------------------------------------------
# Types — custom ASTRA types (genuinely novel concepts)
# ---------------------------------------------------------------------------

# Multi-typed with schema.org supertypes where applicable:
#   ASTRAAnalysis    -> ["Dataset", "ASTRAAnalysis"]
#   ASTRADecision    -> ["DefinedTermSet", "ASTRADecision"]
#   ASTRAOption      -> ["DefinedTerm", "ASTRAOption"]
#   ASTRAInsight     -> ["Claim", "ASTRAInsight"]
#   ASTRARecipe      -> ["CreateAction", "ASTRARecipe"]
#   ASTRAInput       -> ["FormalParameter", "ASTRAInput"]
#   ASTRAOutput      -> ["FormalParameter", "ASTRAOutput"]

TYPE_ANALYSIS = "ASTRAAnalysis"
TYPE_DECISION = "ASTRADecision"
TYPE_OPTION = "ASTRAOption"
TYPE_INPUT = "ASTRAInput"
TYPE_OUTPUT = "ASTRAOutput"
TYPE_UNIVERSE = "ASTRAUniverse"
TYPE_UNIVERSE_SELECTION = "ASTRAUniverseSelection"
TYPE_INSIGHT = "ASTRAInsight"
TYPE_EVIDENCE = "ASTRAEvidence"
TYPE_RECIPE = "ASTRARecipe"
TYPE_RESOURCES = "ASTRAResources"
TYPE_SUCCESS_CRITERION = "ASTRASuccessCriterion"

# ---------------------------------------------------------------------------
# Properties — schema.org standard properties we reuse directly
# ---------------------------------------------------------------------------
# These are standard schema.org property names used as JSON-LD keys.
# Defined as constants for consistency and to make the mapping explicit.

SCHEMA_NAME = "name"
SCHEMA_DESCRIPTION = "description"
SCHEMA_IDENTIFIER = "identifier"
SCHEMA_TEXT = "text"
SCHEMA_VERSION = "version"
SCHEMA_KEYWORDS = "keywords"
SCHEMA_ALTERNATE_NAME = "alternateName"
SCHEMA_IS_BASED_ON = "isBasedOn"
SCHEMA_DATE_CREATED = "dateCreated"
SCHEMA_AUTHOR = "author"
SCHEMA_CONFORMS_TO = "conformsTo"
SCHEMA_RESULT = "result"
SCHEMA_OBJECT = "object"
SCHEMA_COMMENT = "comment"
SCHEMA_PRODUCER = "producer"

# ---------------------------------------------------------------------------
# Properties — custom ASTRA properties (no standard equivalent)
# ---------------------------------------------------------------------------

# Analysis-level
PROP_ASTRA_VERSION = "astraVersion"
PROP_HAS_DECISION = "hasDecision"
PROP_HAS_INPUT = "hasInput"
PROP_HAS_OUTPUT = "hasOutput"
PROP_HAS_PRIOR_INSIGHT = "hasPriorInsight"
PROP_HAS_FINDING = "hasFinding"
PROP_HAS_SUCCESS_CRITERION = "hasSuccessCriterion"

# Decision-level
PROP_HAS_OPTION = "hasOption"
PROP_DEFAULT_OPTION = "defaultOption"
PROP_ACTIVE_WHEN = "activeWhen"
PROP_DELEGATES_TO = "delegatesTo"

# Option-level
PROP_INCOMPATIBLE_WITH = "incompatibleWith"
PROP_REQUIRES_OPTION = "requiresOption"
PROP_SUPPORTS_INSIGHT = "supportsInsight"
PROP_IS_EXCLUDED = "isExcluded"
PROP_EXCLUDED_REASON = "excludedReason"

# Output-level
PROP_OUTPUT_FROM = "outputFrom"
PROP_OUTPUT_TYPE = "outputType"

# Input-level
PROP_INPUT_TYPE = "inputType"
PROP_INPUT_FROM = "inputFrom"
PROP_USE_OUTPUTS = "useOutputs"

# Universe-level
PROP_SELECTS_DECISION = "selectsDecision"
PROP_SELECTS_OPTION = "selectsOption"
PROP_HAS_SELECTION = "hasSelection"

# Recipe-level (on CreateAction)
PROP_HAS_RESOURCES = "hasResources"

# Insight-level
PROP_HAS_EVIDENCE = "hasEvidence"
PROP_IS_DERIVED = "isDerived"
PROP_SCOPE = "scope"

# Evidence-level
PROP_SOURCE_COMMIT = "sourceCommit"

# Success criterion
PROP_CONDITION = "condition"

# Container build spec
PROP_BUILD = "build"
PROP_BUILD_CONTEXT = "buildContext"
PROP_BUILD_ARGS = "buildArgs"

# Resources
PROP_CPUS = "cpus"
PROP_MEMORY = "memory"
PROP_GPUS = "gpus"
PROP_TIME_LIMIT = "timeLimit"

# ---------------------------------------------------------------------------
# ID patterns
# ---------------------------------------------------------------------------

ID_PATTERN = r"^[a-z][a-z0-9_]*$"
UNIVERSE_ID_PATTERN = r"^[a-z][a-z0-9_-]*$"
WHEN_PATTERN = r"^~?[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"


def decision_id(name: str) -> str:
    return f"#decision/{name}"


def option_id(decision_name: str, option_name: str) -> str:
    return f"#decision/{decision_name}/option/{option_name}"


def input_id(name: str) -> str:
    return f"#input/{name}"


def output_id(name: str) -> str:
    return f"#output/{name}"


def recipe_id(output_name: str) -> str:
    return f"#output/{output_name}/recipe"


def insight_id(name: str) -> str:
    return f"#insight/{name}"


def evidence_id(insight_name: str, evidence_name: str) -> str:
    return f"#insight/{insight_name}/evidence/{evidence_name}"


def universe_id(name: str) -> str:
    return f"#universe/{name}"


def selection_id(universe_name: str, index: int) -> str:
    return f"#universe/{universe_name}/sel/{index}"


def resources_id(output_name: str) -> str:
    return f"#output/{output_name}/recipe/resources"


def criterion_id(index: int) -> str:
    return f"#criterion/{index}"


# ---------------------------------------------------------------------------
# ID parsing helpers
# ---------------------------------------------------------------------------


def parse_entity_name(entity_id: str) -> str:
    """Extract the name from an entity @id.

    Examples:
        '#decision/scaling' -> 'scaling'
        '#output/accuracy' -> 'accuracy'
    """
    return entity_id.rsplit("/", 1)[-1]


def parse_decision_from_option(opt_id: str) -> str:
    """Extract the decision name from an option @id.

    Example: '#decision/scaling/option/standard' -> 'scaling'
    """
    parts = opt_id.split("/")
    return parts[1] if len(parts) >= 4 else ""


def ref(entity_id: str) -> dict[str, str]:
    """Create a JSON-LD @id reference."""
    return {"@id": entity_id}


# ---------------------------------------------------------------------------
# JSON-LD value helpers
# ---------------------------------------------------------------------------


def as_list(value: Any) -> list[Any]:
    """Normalize a JSON-LD property value that may be a single item or a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def id_of(value: Any) -> str:
    """Extract the @id string from a JSON-LD reference dict, entity, or string."""
    if isinstance(value, dict):
        return value.get("@id", "")
    if isinstance(value, str):
        return value
    entity_id = getattr(value, "id", None)
    if isinstance(entity_id, str):
        return entity_id
    return ""


def build_subcrate_prefix(sub_name: str, parent_prefix: str) -> str:
    """Build the path prefix for a subcrate in a tree walk."""
    if parent_prefix:
        return f"{parent_prefix}{sub_name}/"
    return f"{sub_name}/"


# ---------------------------------------------------------------------------
# JSON-LD Context
# ---------------------------------------------------------------------------

ASTRA_CONTEXT: dict[str, str | dict[str, str]] = {
    "astra": ASTRA_NS,
    # External vocabularies we reference
    "oa": "http://www.w3.org/ns/oa#",
    "wfrun": WFRUN_NS,
    "FormalParameter": "https://bioschemas.org/FormalParameter",
    # Types
    TYPE_ANALYSIS: f"astra:{TYPE_ANALYSIS}",
    TYPE_DECISION: f"astra:{TYPE_DECISION}",
    TYPE_OPTION: f"astra:{TYPE_OPTION}",
    TYPE_INPUT: f"astra:{TYPE_INPUT}",
    TYPE_OUTPUT: f"astra:{TYPE_OUTPUT}",
    TYPE_UNIVERSE: f"astra:{TYPE_UNIVERSE}",
    TYPE_UNIVERSE_SELECTION: f"astra:{TYPE_UNIVERSE_SELECTION}",
    TYPE_INSIGHT: f"astra:{TYPE_INSIGHT}",
    TYPE_EVIDENCE: f"astra:{TYPE_EVIDENCE}",
    TYPE_RECIPE: f"astra:{TYPE_RECIPE}",
    TYPE_RESOURCES: f"astra:{TYPE_RESOURCES}",
    TYPE_SUCCESS_CRITERION: f"astra:{TYPE_SUCCESS_CRITERION}",
    # Properties with @id range (linked entities)
    PROP_HAS_DECISION: {"@id": f"astra:{PROP_HAS_DECISION}", "@type": "@id"},
    PROP_HAS_INPUT: {"@id": f"astra:{PROP_HAS_INPUT}", "@type": "@id"},
    PROP_HAS_OUTPUT: {"@id": f"astra:{PROP_HAS_OUTPUT}", "@type": "@id"},
    PROP_HAS_PRIOR_INSIGHT: {"@id": f"astra:{PROP_HAS_PRIOR_INSIGHT}", "@type": "@id"},
    PROP_HAS_FINDING: {"@id": f"astra:{PROP_HAS_FINDING}", "@type": "@id"},
    PROP_HAS_SUCCESS_CRITERION: {"@id": f"astra:{PROP_HAS_SUCCESS_CRITERION}", "@type": "@id"},
    PROP_HAS_OPTION: {"@id": f"astra:{PROP_HAS_OPTION}", "@type": "@id"},
    PROP_DEFAULT_OPTION: {"@id": f"astra:{PROP_DEFAULT_OPTION}", "@type": "@id"},
    PROP_DELEGATES_TO: {"@id": f"astra:{PROP_DELEGATES_TO}", "@type": "@id"},
    PROP_INCOMPATIBLE_WITH: {"@id": f"astra:{PROP_INCOMPATIBLE_WITH}", "@type": "@id"},
    PROP_REQUIRES_OPTION: {"@id": f"astra:{PROP_REQUIRES_OPTION}", "@type": "@id"},
    PROP_SUPPORTS_INSIGHT: {"@id": f"astra:{PROP_SUPPORTS_INSIGHT}", "@type": "@id"},
    PROP_SELECTS_DECISION: {"@id": f"astra:{PROP_SELECTS_DECISION}", "@type": "@id"},
    PROP_SELECTS_OPTION: {"@id": f"astra:{PROP_SELECTS_OPTION}", "@type": "@id"},
    PROP_HAS_SELECTION: {"@id": f"astra:{PROP_HAS_SELECTION}", "@type": "@id"},
    PROP_HAS_RESOURCES: {"@id": f"astra:{PROP_HAS_RESOURCES}", "@type": "@id"},
    PROP_HAS_EVIDENCE: {"@id": f"astra:{PROP_HAS_EVIDENCE}", "@type": "@id"},
    # Plain text/value properties (custom ASTRA only)
    PROP_ASTRA_VERSION: f"astra:{PROP_ASTRA_VERSION}",
    PROP_ACTIVE_WHEN: f"astra:{PROP_ACTIVE_WHEN}",
    PROP_IS_EXCLUDED: f"astra:{PROP_IS_EXCLUDED}",
    PROP_EXCLUDED_REASON: f"astra:{PROP_EXCLUDED_REASON}",
    PROP_OUTPUT_FROM: f"astra:{PROP_OUTPUT_FROM}",
    PROP_OUTPUT_TYPE: f"astra:{PROP_OUTPUT_TYPE}",
    PROP_INPUT_TYPE: f"astra:{PROP_INPUT_TYPE}",
    PROP_INPUT_FROM: f"astra:{PROP_INPUT_FROM}",
    PROP_USE_OUTPUTS: f"astra:{PROP_USE_OUTPUTS}",
    PROP_IS_DERIVED: f"astra:{PROP_IS_DERIVED}",
    PROP_SCOPE: f"astra:{PROP_SCOPE}",
    PROP_SOURCE_COMMIT: f"astra:{PROP_SOURCE_COMMIT}",
    PROP_CPUS: f"astra:{PROP_CPUS}",
    PROP_MEMORY: f"astra:{PROP_MEMORY}",
    PROP_GPUS: f"astra:{PROP_GPUS}",
    PROP_TIME_LIMIT: f"astra:{PROP_TIME_LIMIT}",
    PROP_CONDITION: f"astra:{PROP_CONDITION}",
    PROP_BUILD: f"astra:{PROP_BUILD}",
    PROP_BUILD_CONTEXT: f"astra:{PROP_BUILD_CONTEXT}",
    PROP_BUILD_ARGS: f"astra:{PROP_BUILD_ARGS}",
}


def get_context() -> list[str | dict[str, str | dict[str, str]]]:
    """Return the @context array for ASTRA RO-Crates."""
    return [ROCRATE_CONTEXT_URL, ASTRA_CONTEXT]


# ---------------------------------------------------------------------------
# Valid enum values
# ---------------------------------------------------------------------------

OUTPUT_TYPES = {"metric", "figure", "table", "data", "report"}
INPUT_TYPES = {"data", "analysis"}
