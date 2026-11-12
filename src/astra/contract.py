"""The schema layer: astra-spec's JSON Schemas, and the code of each error (Schema files).

`analysis.schema.json` is the contract of an `astra.yaml` and `provenance.schema.json` that of a
record: a document breaks no schema rule exactly when a JSON Schema draft 2019-09 validator
reports no error for it. jsonschema's `Draft201909Validator` checks it here, with one keyword
replaced: `pattern`, whose `$` matches only at the end, as ECMA-262's does.

Each file is read by the schema of the minor version it states, so
`spec_version` is read first. An `astra.yaml` whose well-formed version is outside 0.1 is
astra-tools' `UNSUPPORTED_SPEC_VERSION`, and the schema isn't run; a missing or malformed one
is read by the 0.1 schema, which reports it. A record of a
greater minor version is read by the open schema, and one below 0.1.0 has no schema
(`INVALID_RECORD`).

Each error that makes the document fail is mapped to its code through `rules.json`'s `errors`,
by its absolute keyword location: the schema's `$id`, `#`, the JSON Pointer of the subschema
holding the keyword, found in an index of the schema by object identity, and the keyword. Those
are the errors jsonschema gives: none inside an `if` or a `not`, and a failing `oneOf` as one
error, at the place and with the code of its branches'.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, cast

from astra.diagnostics import Catalogue, Diagnostic, Location, json_pointer

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

    from jsonschema import Draft201909Validator
    from jsonschema.exceptions import ValidationError

    from astra.load import Document

SchemaName = Literal["analysis", "provenance", "provenance.open"]
SCHEMA_NAMES: tuple[SchemaName, ...] = ("analysis", "provenance", "provenance.open")

SUPPORTED = (0, 1)
"""The minor version this astra-tools has the schemas of."""

CODES = frozenset({"UNSUPPORTED_SPEC_VERSION", "INVALID_RECORD"})
"""The codes reported here beside the schema layer's, which `rules.json`'s errors give: one of
astra-tools' own (`diagnostics.OWN`), and a check rule."""

_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
"""A well-formed `spec_version`."""


def schema_file(name: SchemaName) -> Traversable:
    """The JSON Schema `name`, as astra-spec installs it."""
    return files("astra.schema") / "generated" / f"{name}.schema.json"


@dataclass(frozen=True)
class _Schema:
    uri: str  # its `$id`
    pointers: Mapping[int, str]  # the JSON Pointer of every object in it, by id()
    validator: Draft201909Validator  # which keeps the schema, so that no id is reused


@dataclass(frozen=True)
class Contract:
    """The three JSON Schemas, and the catalogue that gives their errors' codes."""

    catalogue: Catalogue
    schemas: Mapping[str, _Schema]

    @classmethod
    def load(cls, catalogue: Catalogue) -> Contract:
        from jsonschema import Draft201909Validator, validators

        keywords = {"pattern": _pattern}
        validator = validators.extend(Draft201909Validator, keywords)  # type: ignore[no-untyped-call]
        schemas: dict[str, _Schema] = {}
        for name in SCHEMA_NAMES:
            content = json.loads(schema_file(name).read_text(encoding="utf-8"))
            schemas[name] = _Schema(content["$id"], _index(content), validator(content))
        return cls(catalogue, MappingProxyType(schemas))

    def check_analysis(self, document: Document, file: str) -> tuple[Diagnostic, ...]:
        """The schema layer's diagnostics for an `astra.yaml`, or its UNSUPPORTED_SPEC_VERSION."""
        version = _version(document.value)
        if version is not None and version[:2] != SUPPORTED:
            message = (
                f"spec_version {document.value['spec_version']} is ASTRA {version[0]}."
                f"{version[1]}, and this astra-tools reads ASTRA 0.1 alone"
            )
            return (self._at(document, file, "UNSUPPORTED_SPEC_VERSION", message),)
        return self._check("analysis", document, file)

    def check_record(self, document: Document, file: str) -> tuple[Diagnostic, ...]:
        """The schema layer's diagnostics for a record, by the schema its minor version picks:
        0.1's, the open one for a greater minor version, and none below 0.1 (INVALID_RECORD)."""
        version = _version(document.value)
        if version is not None and version[:2] < SUPPORTED:
            message = f"records begin at 0.1.0: {document.value['spec_version']} has no schema"
            return (self._at(document, file, "INVALID_RECORD", message),)
        later = version is not None and version[:2] > SUPPORTED
        return self._check("provenance.open" if later else "provenance", document, file)

    def _at(self, document: Document, file: str, code: str, message: str) -> Diagnostic:
        line, column = document.position(["spec_version"]) or (None, None)
        location = Location(file, "/spec_version", line, column)
        return self.catalogue.diagnostic(code, message, location)

    def _check(self, name: SchemaName, document: Document, file: str) -> tuple[Diagnostic, ...]:
        schema = self.schemas[name]
        found = []
        for error in schema.validator.iter_errors(document.value):
            at = schema.pointers.get(id(error.schema))
            keyword = f"{schema.uri}#{at}{json_pointer([str(error.validator)])}"
            code = self.catalogue.errors.get(keyword)
            if at is None or code is None:
                raise LookupError(f"{keyword} isn't in astra-spec's rules.json")
            path = list(error.absolute_path)
            for key, message in _explained(error, at.endswith("/propertyNames")):
                line, column = document.position(path, key) or (None, None)
                location = Location(file, json_pointer(path), line, column, key)
                found.append(self.catalogue.diagnostic(code, message, location))
        # jsonschema gives `required` an error per missing field, and each is explained alike.
        return tuple(dict.fromkeys(found))


def _version(value: Any) -> tuple[int, int, int] | None:
    """The version a document states, if it is a map with a well-formed `spec_version`."""
    stated = value.get("spec_version") if isinstance(value, dict) else None
    match = _VERSION.fullmatch(stated) if isinstance(stated, str) else None
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def _index(schema: Mapping[str, Any]) -> Mapping[int, str]:
    """The JSON Pointer of every object in `schema`, by id()."""
    pointers: dict[int, str] = {}
    todo: list[tuple[Any, str]] = [(schema, "")]
    while todo:
        node, pointer = todo.pop()
        if isinstance(node, dict):
            pointers[id(node)] = pointer
            todo.extend((child, pointer + json_pointer([key])) for key, child in node.items())
        elif isinstance(node, list):
            todo.extend((child, f"{pointer}/{index}") for index, child in enumerate(node))
    return MappingProxyType(pointers)


def _pattern(
    validator: Draft201909Validator, pattern: str, instance: Any, schema: Mapping[str, Any]
) -> Iterator[ValidationError]:
    """JSON Schema's `pattern`, matched as ECMA-262 matches it."""
    from jsonschema.exceptions import ValidationError

    if validator.is_type(instance, "string") and not re.search(_ecma_262(pattern), instance):
        yield ValidationError(f"{instance!r} does not match {pattern!r}")


def _ecma_262(pattern: str) -> str:
    """`pattern` with each `$` outside a character class written `\\Z`: ECMA-262's `$` matches
    only at the end of the value, and Python's also before a final line break."""
    out, in_class, index = [], False, 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            out.append(pattern[index : index + 2])
            index += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "$":
            char = "\\Z"
        out.append(char)
        index += 1
    return "".join(out)


_KINDS: Mapping[str, str] = MappingProxyType(
    {
        "null": "null",
        "boolean": "true or false",
        "integer": "an integer",
        "number": "a number",
        "string": "a string",
        "array": "a list",
        "object": "a map",
    }
)


def _kind(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int):
        return "an integer"
    if isinstance(value, float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    return "a list" if isinstance(value, list) else "a map"


def _subject(path: Sequence[str | int]) -> str:
    if not path:
        return "the document"
    *_, last = path
    return f"`{last}`" if isinstance(last, str) else f"item {last + 1} of {_subject(path[:-1])}"


def _fields(names: Iterable[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def _explained(error: ValidationError, on_key: bool) -> list[tuple[str | None, str]]:
    """Each `(key, message)` the error gives: one per unknown field, naming it, and one for an
    error on a map's key, naming the key; otherwise one, naming no key."""
    keyword, value, expected = (
        error.validator,
        cast(Any, error.instance),
        cast(Any, error.validator_value),
    )
    subject = _subject(list(error.absolute_path))
    if on_key:
        return [(value, f"the key `{value}` doesn't match `{expected}`")]
    if keyword == "additionalProperties":
        known = cast(Mapping[str, Any], error.schema).get("properties", {})
        return [(name, f"`{name}` isn't a field here") for name in value if name not in known]
    if keyword == "type":
        types = [expected] if isinstance(expected, str) else expected
        takes = " or ".join(_KINDS[name] for name in types)
        message = f"{subject} is {_kind(value)}, where it takes {takes}"
    elif keyword == "required":
        message = f"{subject} lacks {_fields(name for name in expected if name not in value)}"
    elif keyword in ("minItems", "minProperties"):
        message = f"{subject} is empty"
    elif keyword == "uniqueItems":
        repeated = next(item for index, item in enumerate(value) if item in value[:index])
        message = f"{subject} holds {json.dumps(repeated)} twice"
    elif keyword == "pattern":
        message = f"{subject} doesn't match `{expected}`: {json.dumps(value)}"
    elif keyword == "minimum":
        message = f"{subject} is {value}, below its minimum of {expected}"
    elif keyword == "enum":
        message = f"{subject} is {json.dumps(value)}, not one of {_fields(expected)}"
    elif keyword == "oneOf":
        names = [name for branch in expected for name in branch.get("required", [])]
        message = f"{subject} takes exactly one of {_fields(names)}"
    elif keyword == "not":
        message = f"{subject} can't have {_fields(expected.get('required', []))} here"
    else:
        message = error.message
    return [(None, message)]
