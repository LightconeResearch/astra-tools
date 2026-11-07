"""The `astra` command line (design §4.12). Each command is a module of its own, imported when
it is run, which imports only click until then: `astra --help` and completion load no library.

Exit codes: 0; 1 when `validate` finds an error, or `info` and `universe` find no stack to show;
2 for a usage error, a broken environment or an internal error.
"""

from __future__ import annotations

import importlib
import json
import os
import traceback
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NoReturn

import click

if TYPE_CHECKING:
    from astra.stack import Stack

COMMANDS = MappingProxyType(
    {
        "cache": "astra.cli.cache",
        "completion": "astra.cli.completion",
        "guide": "astra.cli.guide",
        "info": "astra.cli.info",
        "init": "astra.cli.init",
        "rules": "astra.cli.rules",
        "schema": "astra.cli.schema",
        "spec": "astra.cli.spec",
        "universe": "astra.cli.universe",
        "validate": "astra.cli.validate",
    }
)
"""Each command, by name, with the module whose `command` it is."""

FAILED = 1
USAGE = 2


class _Astra(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(COMMANDS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name not in COMMANDS:
            return None
        command: click.Command = importlib.import_module(COMMANDS[cmd_name]).command
        return command

    def invoke(self, ctx: click.Context) -> Any:
        """Run the command; an exception none of them expects is an internal error (exit 2)."""
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.Abort):
            raise
        except Exception as error:
            if os.environ.get("ASTRA_DEBUG"):
                traceback.print_exception(error)
            click.echo(f"astra: internal error: {type(error).__name__}: {error}", err=True)
            click.echo("This is a bug in astra-tools: please report it.", err=True)
            raise click.exceptions.Exit(USAGE) from None


def fail(message: str) -> NoReturn:
    """Stop with `astra: <message>` and exit 2: the environment is broken, not the analysis."""
    click.echo(f"astra: {message}", err=True)
    raise click.exceptions.Exit(USAGE)


def read_stack(path: Path | None) -> Stack:
    """The stack whose root is the analysis in `path` (`api.bind`). Stops with exit 2 where it
    can't be read, and with exit 1 where its root's file isn't a valid document or it is in no
    repository, so that there is no stack to show."""
    from astra import api
    from astra.cache import CacheError
    from astra.sources.git import GitError

    try:
        bound = api.bind(path)
    except (api.NoAnalysisError, CacheError, GitError) as error:
        fail(str(error))
    except OSError as error:
        fail(f"can't read {error.filename}: {error.strerror}")
    if bound.stack is None:  # OPEN(O23)
        folder = "." if path is None else str(path)
        click.echo(
            "astra: the analysis's astra.yaml isn't a valid document, or isn't in a git "
            f"repository, so there is no stack to show: `astra validate {folder}` says why",
            err=True,
        )
        raise click.exceptions.Exit(FAILED)
    return bound.stack


def write_json(document: Any) -> None:
    """Print `document` as JSON, indented."""
    click.echo(json.dumps(document, indent=2, ensure_ascii=False))


main = click.version_option(package_name="astra-tools")(
    _Astra("astra", help="Validate ASTRA analyses, show their stacks, and read the specification.")
)
