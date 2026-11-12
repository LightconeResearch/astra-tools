"""The field reference behind `astra spec`: the classes, enums and types of ASTRA's files, read
from astra-spec's LinkML sources through linkml-runtime, the extra `[reference]` (Schema
files). Their descriptions are the normative definitions of the fields.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

_TYPES = "https://w3id.org/astra/types"


class ReferenceUnavailable(Exception):  # noqa: N818
    """linkml-runtime isn't installed."""


@dataclass(frozen=True)
class Field:
    """A field of a class, as LinkML induces it."""

    name: str
    range: str
    required: bool
    multivalued: bool
    description: str


@dataclass(frozen=True)
class Term:
    """A class, an enum or a type of ASTRA's files."""

    kind: Literal["class", "enum", "type"]
    name: str
    description: str
    fields: tuple[Field, ...] = ()  # a class's
    values: tuple[tuple[str, str], ...] = ()  # an enum's, with their descriptions
    pattern: str | None = None  # a type's


def load_reference() -> tuple[Term, ...]:
    """Every class, then every enum, then every type of ASTRA's own, from astra-spec's sources.

    Raises ReferenceUnavailable when linkml-runtime isn't installed.
    """
    try:
        from linkml_runtime.linkml_model.meta import SchemaDefinition
        from linkml_runtime.utils.schemaview import SchemaView
    except ImportError:
        raise ReferenceUnavailable(
            "astra spec needs the [reference] extra: pip install 'astra-tools[reference]'"
        ) from None
    view = SchemaView(
        SchemaDefinition(
            id="https://w3id.org/astra/reference",
            name="reference",
            imports=["linkml:types", "analysis", "provenance"],
            default_range="string",
            # Need not exist: the imports are read from its folder, the one holding analysis.yaml
            # (an editable install spreads astra.schema over two folders).
            source_file=str(
                Path(str(files("astra.schema") / "analysis.yaml")).with_name("reference.yaml")
            ),
        )
    )
    classes = [
        Term(
            "class",
            name,
            _text(element.description),
            fields=tuple(
                Field(
                    _text(slot.name),
                    _text(slot.range),
                    bool(slot.required),
                    bool(slot.multivalued),
                    _text(slot.description),
                )
                for slot in view.class_induced_slots(name)
            ),
        )
        for name, element in view.all_classes().items()
    ]
    enums = [
        Term(
            "enum",
            name,
            _text(element.description),
            values=tuple(
                (str(value), _text(meaning.description))
                for value, meaning in element.permissible_values.items()
            ),
        )
        for name, element in view.all_enums().items()
    ]
    types = [
        Term("type", name, _text(element.description), pattern=view.induced_type(name).pattern)
        for name, element in view.all_types().items()
        if element.from_schema == _TYPES
    ]
    return (*classes, *enums, *types)


def lookup(terms: tuple[Term, ...], query: str) -> tuple[Term, ...]:
    """The terms `query` names, whatever its case: a class, enum or type by name; `Class.field`,
    that class with that field alone; a field's name, each class that has it, with it alone."""
    wanted = query.casefold()
    named = tuple(term for term in terms if term.name.casefold() == wanted)
    if named:
        return named
    owner, _, field = wanted.rpartition(".")
    return tuple(
        replace(term, fields=found)
        for term in terms
        if owner in ("", term.name.casefold())
        and (found := tuple(f for f in term.fields if f.name.casefold() == field))
    )


def _text(value: Any) -> str:
    return "" if value is None else str(value)
