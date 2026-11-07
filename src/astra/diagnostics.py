"""Diagnostics, and the rule catalogue they take their levels from (design §3).

The catalogue is astra-spec's `rules.json` (Annex E), read at run time from the namespace
package `astra.schema`: every rule's code, layer, level and statement, and the code of each
JSON Schema error. A `MUST` broken is an error and a `SHOULD` a warning, in every layer (§3).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal

Level = Literal["error", "warning"]


@dataclass(frozen=True)
class Location:
    """Where a diagnostic is: a document, and a place in it."""

    file: str  # the document's path from its repository's top
    pointer: str  # JSON Pointer into it; "" for the whole file
    line: int | None
    column: int | None
    key: str | None = None  # the map key or field the diagnostic names (Annex E)
    commit: str | None = None  # set when the file was read at a commit
    url: str | None = None  # set when it came from a remote


@dataclass(frozen=True)
class Diagnostic:
    """A rule broken: its code, its level from the catalogue, and where."""

    code: str
    level: Level
    message: str
    location: Location
    related: tuple[Location, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Rule:
    """One row of a codes table of Part II, as `rules.json` gives it."""

    code: str
    layer: str  # parse, schema, validator, check or runner
    level: str  # MUST or SHOULD
    statement: str
    source: str  # the section whose table states it, as "§7 Inputs"
    status: str | None = None  # a check rule's status when broken


@dataclass(frozen=True)
class Catalogue:
    """`rules.json`: the rules by code, in the specification's order, and the error map."""

    rules: Mapping[str, Rule]
    errors: Mapping[str, str]  # absolute keyword location -> code
    version: str  # the `$comment` naming the release it was made from

    @classmethod
    def load(cls) -> Catalogue:
        """The catalogue of the installed astra-spec."""
        path = files("astra.schema") / "generated" / "rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = {
            rule["code"]: Rule(
                rule["code"],
                rule["layer"],
                rule["level"],
                rule["statement"],
                rule["source"],
                rule.get("status"),
            )
            for rule in data["rules"]
        }
        return cls(MappingProxyType(rules), MappingProxyType(data["errors"]), data["$comment"])

    def rule(self, code: str) -> Rule:
        """The rule `code` names. A code astra-tools reports that isn't in the catalogue is a
        bug: astra-tools and astra-spec disagree."""
        rule = self.rules.get(code)
        if rule is None:
            raise LookupError(f"{code} isn't in astra-spec's rules.json ({self.version})")
        return rule

    def codes(self, layer: str) -> tuple[str, ...]:
        """The codes of `layer`'s rules, in the specification's order."""
        return tuple(code for code, rule in self.rules.items() if rule.layer == layer)

    def diagnostic(
        self, code: str, message: str, location: Location, related: Iterable[Location] = ()
    ) -> Diagnostic:
        """A diagnostic for `code`, at the level its rule's `MUST` or `SHOULD` gives (§3)."""
        level: Level = "error" if self.rule(code).level == "MUST" else "warning"
        return Diagnostic(code, level, message, location, tuple(related))


def json_pointer(path: Iterable[str | int]) -> str:
    """The JSON Pointer (RFC 6901) of a path of keys and indexes; "" for the whole document."""
    return "".join("/" + str(token).replace("~", "~0").replace("/", "~1") for token in path)
