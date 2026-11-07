"""`astra.yaml` and records, as Annex A reads them (design §4.1).

An `astra.yaml` goes to ruamel.yaml's safe loader, pure Python, with a resolver holding YAML
1.2.2's core schema table (§10.3.2), so that `2026-10-26` is a string, as Annex A reads it. The
loader refuses a repeated key (`DUPLICATE_KEY`); every other error it raises is
`INVALID_SYNTAX`, and so is anything in the loaded value that isn't JSON: a key that isn't a
string, a number that isn't finite, or a value only another tag than the core schema's makes.
The composed node tree gives each value its line and column.

A record is `json.loads`, with hooks that refuse a repeated name (`DUPLICATE_KEY`) and the
`NaN` and `Infinity` it would otherwise take (`INVALID_SYNTAX`).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from ruamel.yaml.resolver import VersionedResolver
from ruamel.yaml.tag import Tag

CODES = frozenset({"INVALID_SYNTAX", "DUPLICATE_KEY"})
"""The parse layer's codes, which this module reports."""

_CORE = "tag:yaml.org,2002:"
_CORE_TABLE = (
    (_CORE + "null", re.compile(r"null|Null|NULL|~|")),
    (_CORE + "bool", re.compile(r"true|True|TRUE|false|False|FALSE")),
    (_CORE + "int", re.compile(r"[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+")),
    (
        _CORE + "float",
        re.compile(
            r"[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?"
            r"|[-+]?(\.inf|\.Inf|\.INF)|\.nan|\.NaN|\.NAN"
        ),
    ),
)
"""YAML 1.2.2 §10.3.2's table: the tag of a plain scalar is that of the first row it matches in
full, and a string if it matches none."""


class _CoreSchema(VersionedResolver):
    """A resolver holding the core schema's table, and nothing else."""

    def resolve(self, kind: Any, value: Any, implicit: Any) -> Any:
        if kind is ScalarNode and implicit[0]:
            for tag, pattern in _CORE_TABLE:
                if pattern.fullmatch(value):
                    return Tag(suffix=tag)
        if kind is MappingNode:
            return self.DEFAULT_MAPPING_TAG
        return self.DEFAULT_SEQUENCE_TAG if kind is SequenceNode else self.DEFAULT_SCALAR_TAG


class ParseError(Exception):
    """A file that breaks a parse rule (§5, Annex A)."""

    def __init__(
        self, code: str, message: str, line: int | None = None, column: int | None = None
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.line, self.column = code, message, line, column


@dataclass(frozen=True)
class Document:
    """A file's JSON value; for an `astra.yaml`, with the node tree its positions come from."""

    value: Any
    tree: Node | None = None

    def position(self, path: Sequence[str | int], key: str | None = None) -> tuple[int, int] | None:
        """The line and column, from 1, of the value at `path`, or of its key `key`; None where
        the tree has no such node, and in a record."""
        node = self.tree
        for token in path:
            if isinstance(node, MappingNode):
                node = next((v for k, v in node.value if k.value == token), None)
            elif isinstance(node, SequenceNode) and isinstance(token, int):
                node = node.value[token] if token < len(node.value) else None
            else:
                return None
        if key is not None:
            entries = node.value if isinstance(node, MappingNode) else []
            node = next((k for k, _ in entries if k.value == key), None)
        if node is None:
            return None
        return node.start_mark.line + 1, node.start_mark.column + 1


def load_yaml(data: bytes) -> Document:
    """The `astra.yaml` whose bytes are `data`; raises ParseError if it breaks a parse rule."""
    yaml = YAML(typ="safe", pure=True)
    yaml.Resolver = _CoreSchema
    try:
        tree = yaml.compose(data)
        value = None if tree is None else yaml.constructor.construct_document(tree)
    except DuplicateKeyError as error:
        found = re.match(r'found duplicate key "(.*?)" with value', error.problem or "")
        key = f"the key `{found[1]}`" if found else "a key"
        _fail("DUPLICATE_KEY", f"{key} is twice in one map", error)
    except Exception as error:  # every other error the loader raises (design §4.1)
        _fail("INVALID_SYNTAX", "this isn't YAML 1.2 as Annex A reads it", error)
    document = Document(value, tree)
    _check_json(document, value, [])
    return document


def _fail(code: str, summary: str, error: Exception) -> NoReturn:
    """Raise the ParseError for the loader's `error`, placed at its mark where it has one: a
    constructor's own error, such as `!!int 1.5`'s ValueError, has none."""
    if isinstance(error, MarkedYAMLError):
        detail = " ".join(part for part in (error.context, error.problem) if part)
        mark = error.problem_mark or error.context_mark
    else:
        detail, mark = str(error).splitlines()[0], None
    message = f"{summary}: {detail}" if code == "INVALID_SYNTAX" else summary
    if mark is None:
        raise ParseError(code, message) from None
    raise ParseError(code, message, mark.line + 1, mark.column + 1) from None


def _check_json(document: Document, value: Any, path: list[str | int]) -> None:
    """Raise INVALID_SYNTAX for the first thing in `value` that isn't JSON (Annex A)."""
    problem = None
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                problem = f"the key {json.dumps(key, default=str)} isn't a string"
                break
            _check_json(document, item, [*path, key])
    elif type(value) is list:
        for index, item in enumerate(value):
            _check_json(document, item, [*path, index])
    elif isinstance(value, float) and not math.isfinite(value):
        problem = f"{value} isn't a finite number, and JSON has no other"
    elif value is not None and type(value) not in (str, int, float, bool):
        problem = f"a {type(value).__name__} isn't JSON: a tag here isn't the core schema's"
    if problem is not None:
        line, column = document.position(path) or (None, None)
        raise ParseError("INVALID_SYNTAX", problem, line, column)


def load_json(data: bytes) -> Document:
    """The record whose bytes are `data`; raises ParseError if it breaks a parse rule."""
    try:
        text = data.decode("utf-8")
        return Document(json.loads(text, object_pairs_hook=_object, parse_constant=_constant))
    except UnicodeDecodeError as error:
        raise ParseError("INVALID_SYNTAX", f"a record is UTF-8, and this isn't: {error}") from None
    except json.JSONDecodeError as error:
        message = f"this isn't JSON: {error.msg}"
        raise ParseError("INVALID_SYNTAX", message, error.lineno, error.colno) from None


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    names: dict[str, Any] = {}
    for name, value in pairs:
        if name in names:
            message = f"the name {json.dumps(name)} is twice in one object"
            raise ParseError("DUPLICATE_KEY", message)
        names[name] = value
    return names


def _constant(text: str) -> NoReturn:
    raise ParseError("INVALID_SYNTAX", f"{text} isn't a JSON number")
