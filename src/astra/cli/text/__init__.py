"""Text output, through rich: the one package of astra-tools that imports it. rich leaves
colour out where `NO_COLOR` is set, or where the output isn't a terminal."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import groupby
from types import MappingProxyType

from rich.console import Console
from rich.text import Text

from astra.diagnostics import Diagnostic, Level, Location

_LEVELS = MappingProxyType({"error": "bold red", "warning": "yellow"})


def console() -> Console:
    """A console on stdout, which highlights nothing it isn't asked to."""
    return Console(highlight=False, soft_wrap=True)


def file_named(location: Location) -> str:
    """A location's file, and, for one read at a commit, the commit and the remote it came
    from."""
    if location.commit is None:
        return location.file
    source = "" if location.url is None else f" from {location.url}"
    return f"{location.file} at {location.commit}{source}"


def rule_line(
    location: Location, level: Level, code: str, message: str, breaks: str | None = None
) -> Text:
    """A rule broken, as `line:col level CODE message` under its file (design §4.12), with the
    parse or schema code a record breaks after its code."""
    line = Text("  ")
    if location.line is not None:
        line.append(f"{location.line}:{location.column} ")
    line.append(level, style=_LEVELS[level])
    line.append(f" {code}", style="bold")
    if breaks is not None:
        line.append(f" ({breaks})")
    line.append(f" {message}")
    return line


def by_file(out: Console, diagnostics: Iterable[Diagnostic]) -> None:
    """Print `diagnostics`, in order of place, grouped by file, each as `rule_line` gives it."""
    for file, grouped in groupby(diagnostics, key=lambda d: file_named(d.location)):
        out.print(Text(file, style="bold"))
        for d in grouped:
            out.print(rule_line(d.location, d.level, d.code, d.message))
