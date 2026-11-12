"""The analysis document, `astra.yaml`, as frozen dataclasses (Elements, the field reference).

`Analysis.from_json` makes one from the JSON value of a document the contract accepted, so
every field has the type its schema gives it. Each class has the fields of its schema class,
named as the schema names them. An optional field left out is None; a list or a map left out
is empty, which the schema allows for neither, so the two never mean different things.
Maps keep their entries in the file's order, which carries no meaning.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeVar

T = TypeVar("T")

_NONE: Mapping[str, Any] = MappingProxyType({})


def _empty() -> Any:
    return _NONE


def _read(cls: type[T], value: Mapping[str, Any], **nested: Callable[[Any], Any]) -> T:
    """`cls` holding `value`'s fields: each one `nested` names made by its function, and any
    other list, of strings, as a tuple."""
    fields = {
        name: nested[name](item) if name in nested else tuple(item) if type(item) is list else item
        for name, item in value.items()
    }
    return cls(**fields)


def _map(make: Callable[[Any], T]) -> Callable[[Any], Mapping[str, T]]:
    return lambda value: MappingProxyType({key: make(item) for key, item in value.items()})


@dataclass(frozen=True)
class Input:
    """A file the analysis reads."""

    path: str
    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Input:
        return _read(cls, value)


@dataclass(frozen=True)
class Option:
    """One of a decision's options."""

    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    excluded: str | None = None
    requires: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()
    insights: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Option:
        return _read(cls, value)


@dataclass(frozen=True)
class Decision:
    """A choice the analysis makes, between its options."""

    options: Mapping[str, Option]
    label: str | None = None
    rationale: str | None = None
    tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Decision:
        return _read(cls, value, options=_map(Option.from_json))


@dataclass(frozen=True)
class Resources:
    """What a recipe asks for."""

    cpus: float | None = None
    memory: str | None = None
    time_limit: str | None = None
    disk: str | None = None
    gpus: int | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Resources:
        return _read(cls, value)


@dataclass(frozen=True)
class Recipe:
    """How an output is made: a command, a template."""

    command: str
    resources: Resources | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Recipe:
        return _read(cls, value, resources=Resources.from_json)


@dataclass(frozen=True)
class Output:
    """An entry of `outputs` (Elements): an output, with a `type`, a `format` and a `recipe`; or
    a switch, with a `switch` and `cases` and none of those (`INVALID_SWITCH`)."""

    type: str | None = None
    format: str | None = None
    recipe: Recipe | None = None
    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    switch: str | None = None  # a decision's address
    cases: Mapping[str, str] = field(default_factory=_empty)  # option id -> reference

    @property
    def is_switch(self) -> bool:
        return self.switch is not None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Output:
        return _read(cls, value, recipe=Recipe.from_json, cases=MappingProxyType)


@dataclass(frozen=True)
class Universe:
    """An entry of `universes`: a universe, or an import, which has `analysis` and `universe`
    and selects nothing."""

    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    decisions: Mapping[str, str] = field(default_factory=_empty)  # address -> option id
    derived_from: str | None = None
    analysis: str | None = None
    universe: str | None = None

    @property
    def is_import(self) -> bool:
        return self.analysis is not None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Universe:
        return _read(cls, value, decisions=MappingProxyType)


@dataclass(frozen=True)
class TextQuoteSelector:
    """A passage quoted exactly."""

    exact: str
    prefix: str | None = None
    suffix: str | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> TextQuoteSelector:
        return _read(cls, value)


@dataclass(frozen=True)
class FragmentSelector:
    """A place in a work or an output, as a fragment identifier."""

    value: str
    conforms_to: str | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> FragmentSelector:
        return _read(cls, value)


@dataclass(frozen=True)
class Evidence:
    """What a claim rests on: a work by its `doi`, or an output as an `artifact`."""

    doi: str | None = None
    version: int | None = None
    artifact: str | None = None
    quote: TextQuoteSelector | None = None
    location: FragmentSelector | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Evidence:
        quote, location = TextQuoteSelector.from_json, FragmentSelector.from_json
        return _read(cls, value, quote=quote, location=location)


@dataclass(frozen=True)
class Insight:
    """A claim backed by evidence."""

    claim: str
    evidence: tuple[Evidence, ...]
    label: str | None = None
    description: str | None = None
    scope: str | None = None
    tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Insight:
        return _read(cls, value, evidence=lambda items: tuple(map(Evidence.from_json, items)))


@dataclass(frozen=True)
class AnalysisDeclaration:
    """An entry of `analyses`: a `path` or a `url`, and maybe a `commit`."""

    path: str | None = None
    url: str | None = None
    commit: str | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> AnalysisDeclaration:
        return _read(cls, value)


@dataclass(frozen=True)
class Analysis:
    """The content of an `astra.yaml`."""

    spec_version: str
    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    inputs: Mapping[str, Input] = field(default_factory=_empty)
    outputs: Mapping[str, Output] = field(default_factory=_empty)
    decisions: Mapping[str, Decision] = field(default_factory=_empty)
    universes: Mapping[str, Universe] = field(default_factory=_empty)
    analyses: Mapping[str, AnalysisDeclaration] = field(default_factory=_empty)
    prior_insights: Mapping[str, Insight] = field(default_factory=_empty)
    findings: Mapping[str, Insight] = field(default_factory=_empty)

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Analysis:
        """The analysis whose JSON value, accepted by the contract, is `value`."""
        return _read(
            cls,
            value,
            outputs=_map(Output.from_json),
            inputs=_map(Input.from_json),
            decisions=_map(Decision.from_json),
            universes=_map(Universe.from_json),
            analyses=_map(AnalysisDeclaration.from_json),
            prior_insights=_map(Insight.from_json),
            findings=_map(Insight.from_json),
        )
