"""Text output, through rich: the one package of astra-tools that imports it. rich leaves
colour out where `NO_COLOR` is set, or where the output isn't a terminal."""

from __future__ import annotations

from rich.console import Console


def console() -> Console:
    """A console on stdout, which highlights nothing it isn't asked to."""
    return Console(highlight=False, soft_wrap=True)
