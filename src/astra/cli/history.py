"""`astra history timeline ADDR | lineage ADDR [--used-by] | find (--hash H | --environment IRI)
| get ADDR@REV`, each with `[PATH]`: what git holds of the records of the planned results
(design §6 *Phase 4*, §4.12). Text alone, as `info` and `universe` are; `get` writes the bytes.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

import click

from astra.cli import FAILED, environment, write_report


@click.group("history")
def command() -> None:
    """Show what git holds of the records of an analysis's planned results.

    ADDR is a result's address, as its record gives it (`output1#u1`, `output2`): `astra plan`
    lists them. PATH is the analysis's folder, the current one by default. A record's versions
    are its file at each commit along HEAD's history that changed it, in the repository that
    holds the analysis the result belongs to. Each command exits 0 when it answers; 1 when the
    analysis breaks a MUST, which is shown as `astra validate` shows it, or what is asked for
    isn't in git; and 2 where ADDR names no planned result, REV names no commit, or the
    analysis can't be read.
    """


@contextlib.contextmanager
def _answering(hint: str) -> Iterator[None]:
    """Stop with exit 1 where the analysis breaks a MUST or what is asked for isn't in git, and
    with exit 2 where `hint`, the argument, names nothing or the analysis can't be read."""
    from astra import api

    with environment():
        try:
            yield
        except api.InvalidAnalysisError as error:
            write_report(error.report, False)
            raise click.exceptions.Exit(FAILED) from None
        except api.RequestError as error:
            raise click.BadParameter(str(error), param_hint=hint) from None
        except api.NotInHistoryError as error:
            _missing(str(error))


def _missing(message: str) -> NoReturn:
    """Stop with `astra: <message>` and exit 1: what is asked for isn't in git."""
    click.echo(f"astra: {message}", err=True)
    raise click.exceptions.Exit(FAILED)


@command.command("timeline")
@click.argument("address", metavar="ADDR")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def timeline(address: str, path: Path | None) -> None:
    """Show each version of the record of the result at ADDR, newest first: the commit that
    changed it, and the hash, size, commit, end and environment it gives."""
    from astra import api
    from astra.cli.text.history import show_versions

    with _answering("ADDR"):
        versions = api.history(path).timeline(address)
    if not versions:
        _missing(f"no record of `{address}` is in HEAD's history")
    show_versions(versions)  # text alone


@command.command("lineage")
@click.argument("address", metavar="ADDR")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--used-by", is_flag=True, help="Show what uses it instead, by their records.")
def lineage(address: str, path: Path | None, used_by: bool) -> None:
    """Show what the result at ADDR was made from, as its record at HEAD gives it: each entry
    with the hash and size recorded and, for a planned result, the version of its record that
    gives them, and what that was made from, down to the input files. With --used-by, the
    planned results whose records at HEAD list it instead."""
    from astra import api
    from astra.cli.text.history import show_lineage
    from astra.records import Record

    with _answering("ADDR"):
        found = api.history(path).lineage(address, used_by=used_by)
    if found.version is None:
        _missing(f"no record of `{address}` is in HEAD's history")
    show_lineage(found, used_by)  # text alone
    if not isinstance(found.version.record, Record):
        raise click.exceptions.Exit(FAILED)


@command.command("find")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--hash", "content_hash", metavar="H", help="A content hash, as `sha256:<hex>`.")
@click.option("--environment", "iri", metavar="IRI", help="An environment's IRI.")
def find(path: Path | None, content_hash: str | None, iri: str | None) -> None:
    """Show the versions of the planned results' records whose bytes have the hash H, or whose
    environment is IRI."""
    from astra import api
    from astra.cli.text.history import show_versions

    if (content_hash is None) == (iri is None):
        raise click.UsageError("give one of --hash H and --environment IRI")
    with _answering("--hash"):
        versions = api.history(path).find(content_hash=content_hash, environment=iri)
    if not versions:
        _missing(f"no version of a planned result's record has {content_hash or iri}")
    show_versions(versions)  # text alone


@command.command("get")
@click.argument("asked", metavar="ADDR@REV")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def get(asked: str, path: Path | None) -> None:
    """Write to stdout the bytes the result at ADDR had at the commit REV names (a commit, a
    branch, a tag) in the repository that holds its analysis: those at its default place there,
    checked against its record there."""
    from astra import api

    address, at, revision = asked.partition("@")  # an address holds no `@` (Annex C)
    if not (address and at and revision):
        raise click.BadParameter("give a result's address and a revision", param_hint="ADDR@REV")
    with _answering("ADDR@REV"):
        data = api.history(path).get(address, revision)
    click.echo(data, nl=False)  # bytes, written as they are
