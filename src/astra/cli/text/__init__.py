"""Text output, through rich: the one package of astra-tools that imports it. rich leaves
colour out where `NO_COLOR` is set, or where the output isn't a terminal."""

from __future__ import annotations

from rich.console import Console

from astra.diagnostics import Location


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
