"""§13 Pins: no rule is checked here. The two this module held went with `when`; it stays,
reporting no code, as the home of §13's rules on pins."""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context

CODES: frozenset[str] = frozenset()


def check(context: Context) -> Iterator[Diagnostic]:
    """Nothing yet: the catalogue has no rule for this module."""
    yield from ()
