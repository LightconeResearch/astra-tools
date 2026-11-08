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
    """Every diagnostic of every rule module. A `MUST` this root's pass finds in the files of
    an analysis from a commit, which isn't among those it breaks as its own root there, has the
    declarations that lead to it as related places (`commits.related`, design §3)."""
    judged = list(commits.check(context))
    found = [d for module in MODULES if module is not commits for d in module.check(context)]
    return [*commits.related(context, found, set(judged)), *judged]
