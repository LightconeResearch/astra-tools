"""The validator rules, one module per section of Part II whose codes table states them
(design §4.4).

A rule module has `CODES`, the codes it reports, and `check(context)`, the diagnostics it
finds in a `Context`. It plugs in by being listed in `MODULES`. `validate()` lists every
validator code of `rules.json` that no module declares as `unchecked` (design §3).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from astra.diagnostics import Diagnostic
from astra.rules import (
    commits,
    decisions,
    declarations,
    driving,
    inputs,
    insights,
    names,
    outputs,
    pins,
    recipes,
    universes,
)
from astra.rules.context import Context


class RuleModule(Protocol):
    CODES: frozenset[str]

    def check(self, context: Context) -> Iterable[Diagnostic]: ...


MODULES: tuple[RuleModule, ...] = (
    names,
    inputs,
    decisions,
    outputs,
    recipes,
    universes,
    pins,
    insights,
    declarations,
    driving,
    commits,
)

CODES = frozenset(code for module in MODULES for code in module.CODES)
"""The validator codes the rules report."""


def check(context: Context) -> list[Diagnostic]:
    """Every diagnostic of every rule module."""
    return [diagnostic for module in MODULES for diagnostic in module.check(context)]
