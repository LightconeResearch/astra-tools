from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.7.0"
version = "1.0"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'astra',
     'default_range': 'string',
     'description': 'Declarative specification format for scientific analyses. '
                    'Defines the structure for analyses with inputs, outputs, '
                    'decisions, insights, universes, and self-similar '
                    'sub-analyses.',
     'id': 'https://w3id.org/astra/schema',
     'imports': ['linkml:types'],
     'license': 'https://creativecommons.org/licenses/by/4.0/',
     'name': 'astra',
     'prefixes': {'astra': {'prefix_prefix': 'astra',
                            'prefix_reference': 'https://w3id.org/astra/terms/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'schema': {'prefix_prefix': 'schema',
                             'prefix_reference': 'http://schema.org/'}},
     'source_file': 'src/astra/schema/astra.yaml',
     'title': 'ASTRA: Agentic Schema for Transparent Research Analysis',
     'types': {'AstraId': {'description': 'Lowercase identifier (letters, digits, '
                                          'underscores)',
                           'from_schema': 'https://w3id.org/astra/schema',
                           'name': 'AstraId',
                           'pattern': '^[a-z][a-z0-9_]*$',
                           'typeof': 'string'},
               'ConstraintRef': {'description': 'Constraint reference in '
                                                'decision.option format',
                                 'from_schema': 'https://w3id.org/astra/schema',
                                 'name': 'ConstraintRef',
                                 'pattern': '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$',
                                 'typeof': 'string'},
               'DoiString': {'description': 'DOI identifier (e.g. 10.1234/example)',
                             'from_schema': 'https://w3id.org/astra/schema',
                             'name': 'DoiString',
                             'pattern': '^10\\.\\d{4,}/.*$',
                             'typeof': 'string'},
               'SemVer': {'description': 'Semantic version string (e.g. 1.0, '
                                         '1.0.0)',
                          'from_schema': 'https://w3id.org/astra/schema',
                          'name': 'SemVer',
                          'pattern': '^\\d+\\.\\d+(\\.\\d+)?$',
                          'typeof': 'string'},
               'UniverseId': {'description': 'Lowercase identifier (letters, '
                                             'digits, underscores, hyphens)',
                              'from_schema': 'https://w3id.org/astra/schema',
                              'name': 'UniverseId',
                              'pattern': '^[a-z][a-z0-9_-]*$',
                              'typeof': 'string'},
               'WhenCondition': {'description': 'Condition in [~]decision.option '
                                                'format',
                                 'from_schema': 'https://w3id.org/astra/schema',
                                 'name': 'WhenCondition',
                                 'pattern': '^~?[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$',
                                 'typeof': 'string'}}} )

class OutputTypeEnum(str, Enum):
    metric = "metric"
    """
    Numeric or categorical measurement
    """
    figure = "figure"
    """
    Visualization
    """
    table = "table"
    """
    Structured tabular data
    """
    data = "data"
    """
    Processed data files
    """
    report = "report"
    """
    Text document or synthesis
    """


class InputTypeEnum(str, Enum):
    data = "data"
    """
    Raw data input
    """
    analysis = "analysis"
    """
    Reference to a previous analysis
    """


class ChecksumAlgorithm(str, Enum):
    sha256 = "sha256"
    sha512 = "sha512"
    md5 = "md5"



class NamedEntity(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'schema:Thing',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixin': True})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Analysis(NamedEntity):
    """
    Root entity of an ASTRA analysis. Self-similar: can contain sub-analyses with the same structure.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Analysis',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity'],
         'tree_root': True})

    astra_version: str = Field(default=..., description="""ASTRA specification version""", json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis'], 'slot_uri': 'astra:astraVersion'} })
    authors: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis'], 'slot_uri': 'schema:author'} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis', 'Decision', 'Insight'],
         'slot_uri': 'schema:keywords'} })
    container: Optional[str] = Field(default=None, description="""Default container image for recipes""", json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis', 'Recipe']} })
    inputs: Optional[list[Input]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis']} })
    outputs: Optional[list[Output]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis']} })
    decisions: Optional[dict[str, Decision]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis'], 'slot_uri': 'astra:hasDecision'} })
    prior_insights: Optional[dict[str, Insight]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis'], 'slot_uri': 'astra:hasPriorInsight'} })
    findings: Optional[dict[str, Insight]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis'], 'slot_uri': 'astra:hasFinding'} })
    success_criteria: Optional[list[SuccessCriterion]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis']} })
    analyses: Optional[dict[str, Analysis]] = Field(default=None, description="""Sub-analyses (self-similar nesting)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis']} })
    universes: Optional[dict[str, Universe]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis']} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Input(NamedEntity):
    """
    An input to the analysis (data source or analysis reference)
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Input',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity']})

    type: InputTypeEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Input', 'Output'], 'slot_uri': 'astra:inputType'} })
    source: Optional[str] = Field(default=None, description="""Path or URI for data inputs""", json_schema_extra = { "linkml_meta": {'domain_of': ['Input'], 'slot_uri': 'schema:identifier'} })
    based_on: Optional[str] = Field(default=None, description="""Reference to another analysis""", json_schema_extra = { "linkml_meta": {'domain_of': ['Input'], 'slot_uri': 'schema:isBasedOn'} })
    ref_version: Optional[str] = Field(default=None, description="""Version of the referenced analysis""", json_schema_extra = { "linkml_meta": {'domain_of': ['Input'], 'slot_uri': 'schema:version'} })
    use_outputs: Optional[list[str]] = Field(default=None, description="""Specific output IDs from the referenced analysis""", json_schema_extra = { "linkml_meta": {'domain_of': ['Input'], 'slot_uri': 'astra:useOutputs'} })
    input_from: Optional[str] = Field(default=None, description="""Parent input or sibling output reference""", json_schema_extra = { "linkml_meta": {'domain_of': ['Input'], 'slot_uri': 'astra:inputFrom'} })
    checksum: Optional[Checksum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Input', 'Evidence']} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Output(NamedEntity):
    """
    A declared output of the analysis
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Output',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity']})

    type: OutputTypeEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Input', 'Output'], 'slot_uri': 'astra:outputType'} })
    recipe: Optional[Recipe] = Field(default=None, description="""Build rule for producing this output""", json_schema_extra = { "linkml_meta": {'domain_of': ['Output']} })
    active_when: Optional[list[str]] = Field(default=None, description="""Conditions for this output to be active""", json_schema_extra = { "linkml_meta": {'domain_of': ['Output', 'Decision'], 'slot_uri': 'astra:activeWhen'} })
    output_from: Optional[str] = Field(default=None, description="""Sub-analysis output reference (e.g. classification.accuracy)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Output'], 'slot_uri': 'astra:outputFrom'} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Recipe(ConfiguredBaseModel):
    """
    Build rule for producing an output
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Recipe', 'from_schema': 'https://w3id.org/astra/schema'})

    command: str = Field(default=..., description="""Shell command to execute""", json_schema_extra = { "linkml_meta": {'domain_of': ['Recipe']} })
    depends_on: Optional[list[str]] = Field(default=None, description="""Output IDs this recipe depends on""", json_schema_extra = { "linkml_meta": {'domain_of': ['Recipe']} })
    container: Optional[str] = Field(default=None, description="""Container image override""", json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis', 'Recipe']} })
    resources: Optional[Resources] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Recipe']} })


class Resources(ConfiguredBaseModel):
    """
    Compute resource requirements
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Resources', 'from_schema': 'https://w3id.org/astra/schema'})

    cpus: Optional[int] = Field(default=None, ge=1, json_schema_extra = { "linkml_meta": {'domain_of': ['Resources'], 'slot_uri': 'astra:cpus'} })
    memory: Optional[str] = Field(default=None, description="""Memory requirement (e.g. 8GB)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Resources'], 'slot_uri': 'astra:memory'} })
    gpus: Optional[int] = Field(default=None, ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['Resources'], 'slot_uri': 'astra:gpus'} })
    time_limit: Optional[str] = Field(default=None, description="""Time limit (e.g. 2h, 30m)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Resources'], 'slot_uri': 'astra:timeLimit'} })


class Decision(NamedEntity):
    """
    A choice point with multiple options
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Decision',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity'],
         'rules': [{'description': 'Delegated decisions must not have options or '
                                   'default',
                    'postconditions': {'slot_conditions': {'default': {'name': 'default',
                                                                       'value_presence': 'ABSENT'},
                                                           'options': {'name': 'options',
                                                                       'value_presence': 'ABSENT'}}},
                    'preconditions': {'slot_conditions': {'delegates_to': {'name': 'delegates_to',
                                                                           'required': True}}}}]})

    options: Optional[dict[str, Option]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Decision'], 'slot_uri': 'astra:hasOption'} })
    default: Optional[str] = Field(default=None, description="""ID of the default option""", json_schema_extra = { "linkml_meta": {'domain_of': ['Decision'], 'slot_uri': 'astra:defaultOption'} })
    rationale: Optional[str] = Field(default=None, description="""Why this decision exists (alias for description)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Decision']} })
    active_when: Optional[list[str]] = Field(default=None, description="""Conditions for this decision to be active""", json_schema_extra = { "linkml_meta": {'domain_of': ['Output', 'Decision'], 'slot_uri': 'astra:activeWhen'} })
    delegates_to: Optional[str] = Field(default=None, description="""Parent decision reference (e.g. ../random_seed)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Decision'], 'slot_uri': 'astra:delegatesTo'} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis', 'Decision', 'Insight'],
         'slot_uri': 'schema:keywords'} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Option(NamedEntity):
    """
    One selectable choice within a decision
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Option',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity']})

    insights: Optional[list[str]] = Field(default=None, description="""Insight IDs that support this option""", json_schema_extra = { "linkml_meta": {'domain_of': ['Option'], 'slot_uri': 'astra:supportsInsight'} })
    incompatible_with: Optional[list[str]] = Field(default=None, description="""decision.option pairs that conflict""", json_schema_extra = { "linkml_meta": {'domain_of': ['Option'], 'slot_uri': 'astra:incompatibleWith'} })
    requires: Optional[list[str]] = Field(default=None, description="""decision.option pairs that must coexist""", json_schema_extra = { "linkml_meta": {'domain_of': ['Option'], 'slot_uri': 'astra:requiresOption'} })
    is_excluded: Optional[bool] = Field(default=None, description="""Whether this option was considered and rejected""", json_schema_extra = { "linkml_meta": {'domain_of': ['Option'], 'slot_uri': 'astra:isExcluded'} })
    excluded_reason: Optional[str] = Field(default=None, description="""Why this option was excluded""", json_schema_extra = { "linkml_meta": {'domain_of': ['Option'], 'slot_uri': 'astra:excludedReason'} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Insight(NamedEntity):
    """
    Scientific claim backed by evidence
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Insight',
         'from_schema': 'https://w3id.org/astra/schema',
         'mixins': ['NamedEntity']})

    claim: str = Field(default=..., description="""The claim text (1-2 sentences)""", json_schema_extra = { "linkml_meta": {'domain_of': ['Insight', 'SuccessCriterion'], 'slot_uri': 'schema:text'} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Insight'], 'slot_uri': 'schema:dateCreated'} })
    evidence: list[Evidence] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Insight'], 'slot_uri': 'astra:hasEvidence'} })
    is_derived: Optional[bool] = Field(default=None, description="""Whether this insight is synthesized/inferred""", json_schema_extra = { "linkml_meta": {'domain_of': ['Insight'], 'slot_uri': 'astra:isDerived'} })
    scope: Optional[str] = Field(default=None, description="""Applicability conditions""", json_schema_extra = { "linkml_meta": {'domain_of': ['Insight'], 'slot_uri': 'astra:scope'} })
    notes: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Insight'], 'slot_uri': 'schema:comment'} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Analysis', 'Decision', 'Insight'],
         'slot_uri': 'schema:keywords'} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:name'} })
    label: Optional[str] = Field(default=None, description="""Human-readable label""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector'],
         'slot_uri': 'schema:alternateName'} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe'], 'slot_uri': 'schema:description'} })


class Evidence(ConfiguredBaseModel):
    """
    Evidence source with content selectors
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Evidence', 'from_schema': 'https://w3id.org/astra/schema'})

    id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    doi: Optional[str] = Field(default=None, description="""DOI for literature evidence""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    version: Optional[int] = Field(default=None, description="""Version number (e.g. arXiv version)""", ge=1, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    artifact: Optional[str] = Field(default=None, description="""Output ID for artifact evidence""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    source_commit: Optional[str] = Field(default=None, description="""Git commit that produced the artifact""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'astra:sourceCommit'} })
    snapshot: Optional[str] = Field(default=None, description="""Path to immutable artifact copy""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    checksum: Optional[Checksum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Input', 'Evidence']} })
    quote: Optional[QuoteSelector] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    figure: Optional[FigureSelector] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    table: Optional[TableSelector] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    location: Optional[LocationSelector] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })


class QuoteSelector(ConfiguredBaseModel):
    """
    W3C TextQuoteSelector
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/astra/schema'})

    exact: str = Field(default=..., description="""Exact quoted text""", json_schema_extra = { "linkml_meta": {'domain_of': ['QuoteSelector']} })
    prefix: Optional[str] = Field(default=None, description="""Text before the quote for disambiguation""", json_schema_extra = { "linkml_meta": {'domain_of': ['QuoteSelector']} })
    suffix: Optional[str] = Field(default=None, description="""Text after the quote for disambiguation""", json_schema_extra = { "linkml_meta": {'domain_of': ['QuoteSelector']} })


class FigureSelector(ConfiguredBaseModel):
    """
    Reference to a figure in a document
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/astra/schema'})

    label: str = Field(default=..., description="""Figure label (e.g. Figure 3a)""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector']} })
    caption: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['FigureSelector', 'TableSelector']} })


class TableSelector(ConfiguredBaseModel):
    """
    Reference to a table in a document
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/astra/schema'})

    label: str = Field(default=..., description="""Table label (e.g. Table 2)""", json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'FigureSelector', 'TableSelector']} })
    caption: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['FigureSelector', 'TableSelector']} })
    region: Optional[str] = Field(default=None, description="""Specific region (e.g. row 3, accuracy column)""", json_schema_extra = { "linkml_meta": {'domain_of': ['TableSelector']} })


class LocationSelector(ConfiguredBaseModel):
    """
    Location hint (page number)
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/astra/schema'})

    page: Optional[int] = Field(default=None, description="""1-indexed page number""", ge=1, json_schema_extra = { "linkml_meta": {'domain_of': ['LocationSelector']} })


class Checksum(ConfiguredBaseModel):
    """
    Data integrity checksum
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Checksum', 'from_schema': 'https://w3id.org/astra/schema'})

    algorithm: ChecksumAlgorithm = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Checksum']} })
    value: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Checksum']} })


class Universe(ConfiguredBaseModel):
    """
    One complete set of decision selections
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:Universe', 'from_schema': 'https://w3id.org/astra/schema'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['NamedEntity', 'Universe']} })
    selections: Optional[list[UniverseSelection]] = Field(default=None, description="""List of decision=option bindings. In YAML authoring format, can also be written as a flat dict {decision: option} which the loader normalizes to this list form.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Universe'], 'slot_uri': 'astra:hasSelection'} })


class UniverseSelection(ConfiguredBaseModel):
    """
    One decision=option binding in a universe
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:UniverseSelection',
         'from_schema': 'https://w3id.org/astra/schema'})

    decision: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['UniverseSelection'], 'slot_uri': 'astra:selectsDecision'} })
    option: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['UniverseSelection'], 'slot_uri': 'astra:selectsOption'} })


class SuccessCriterion(ConfiguredBaseModel):
    """
    Testable success condition
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'astra:SuccessCriterion',
         'from_schema': 'https://w3id.org/astra/schema',
         'rules': [{'description': 'condition requires output',
                    'postconditions': {'slot_conditions': {'output': {'name': 'output',
                                                                      'required': True}}},
                    'preconditions': {'slot_conditions': {'condition': {'name': 'condition',
                                                                        'required': True}}}}]})

    claim: str = Field(default=..., description="""Human-readable statement of the criterion""", json_schema_extra = { "linkml_meta": {'domain_of': ['Insight', 'SuccessCriterion']} })
    output: Optional[str] = Field(default=None, description="""Output ID to check""", json_schema_extra = { "linkml_meta": {'domain_of': ['SuccessCriterion']} })
    condition: Optional[str] = Field(default=None, description="""Testable condition expression (e.g. value > 0.95)""", json_schema_extra = { "linkml_meta": {'domain_of': ['SuccessCriterion'], 'slot_uri': 'astra:condition'} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
NamedEntity.model_rebuild()
Analysis.model_rebuild()
Input.model_rebuild()
Output.model_rebuild()
Recipe.model_rebuild()
Resources.model_rebuild()
Decision.model_rebuild()
Option.model_rebuild()
Insight.model_rebuild()
Evidence.model_rebuild()
QuoteSelector.model_rebuild()
FigureSelector.model_rebuild()
TableSelector.model_rebuild()
LocationSelector.model_rebuild()
Checksum.model_rebuild()
Universe.model_rebuild()
UniverseSelection.model_rebuild()
SuccessCriterion.model_rebuild()
