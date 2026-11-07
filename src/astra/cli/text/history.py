"""History as text: a record's versions, each under the commit that changed it, with what it
gives or the rules it breaks; a lineage as a tree, each entry with the hash and size recorded and
what they are; and what uses a result, by their records."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from astra.cli.text import console, rule_line
from astra.hashing import Digest
from astra.history import Lineage, Link, Version
from astra.records import Record


def show_versions(versions: tuple[Version, ...]) -> None:
    """Versions of records, each result's under its address and record's path."""
    out = console()
    for at, version in enumerate(versions):
        if at == 0 or version.place != versions[at - 1].place:
            out.print(Text(f"{version.place.address}  {version.place.record}", style="bold"))
        _version(out, version)
    out.print(f"{len(versions)} version(s)")


def show_lineage(lineage: Lineage, used_by: bool) -> None:
    """A result's record at HEAD, then what it was made from, or what uses it."""
    out = console()
    assert lineage.version is not None
    out.print(Text(f"{lineage.place.address}  {lineage.place.record}", style="bold"))
    _version(out, lineage.version)
    if not isinstance(lineage.version.record, Record):
        return
    if not used_by:
        out.print("made from" if lineage.inputs else "made from nothing")
        for link in lineage.inputs:
            _link(out, link, "  ")
        return
    out.print("used by" if lineage.users else "used by no planned result's record at HEAD")
    for use in lineage.users:
        line = Text(f"  {use.version.place.address}", style="bold")
        line.append(f", its record of {use.version.commit}, through `{use.entry}`: ")
        line.append(_digest(use.digest))
        out.print(line)
        out.print(Text(f"    {_read(lineage.place.address, use.read)}"))


def _version(out: Console, version: Version) -> None:
    """A version, under the commit that changed it: what its record gives, or the rules it
    breaks, or that the commit removed it."""
    out.print(Text(f"  {version.commit}"))
    record = version.record
    if record is None:
        out.print(Text("    removed", style="dim"))
    elif isinstance(record, tuple):
        for broken in record:
            said = rule_line(broken.location, broken.level, broken.code, broken.message)
            out.print(Text("  ").append_text(said))
    else:
        out.print(Text(f"    bytes        {_digest(record.digest)}"))
        out.print(Text(f"    made at      {record.commit}"))
        if record.finished is not None:
            out.print(Text(f"    finished     {record.finished}"))
        out.print(Text(f"    environment  {record.environment}"))


def _link(out: Console, link: Link, indent: str) -> None:
    """An entry of a record's `inputs`, what it read, and what that was made from."""
    line = Text(f"{indent}{link.entry}", style="bold")
    line.append(f": {_digest(link.digest)}")
    out.print(line)
    if link.path is not None:
        out.print(Text(f"{indent}  the file {link.path}"))
    elif link.place is None:
        out.print(Text(f"{indent}  an entry its output no longer lists", style="dim"))
    else:
        out.print(Text(f"{indent}  {_read(link.place.address, link.version)}"))
    for below in link.inputs:
        _link(out, below, indent + "  ")


def _read(address: str, version: Version | None) -> str:
    """Which version of the record of `address` gives the hash and size recorded."""
    if version is None:
        return f"no version of {address}'s record gives them"
    record = version.record
    assert isinstance(record, Record)
    return f"{address}'s record of {version.commit}, made at {record.commit}"


def _digest(digest: Digest) -> str:
    return f"{digest.content_hash}, {digest.size} byte(s)"
