"""The `astra` command line (design §4.12). Each command is a module of its own, imported when
it is run, which imports only click until then: `astra --help` and completion load no library.

Exit codes: 0; 1 when `validate` finds an error; 2 for a usage error, a broken environment or
an internal error.
"""

from __future__ import annotations

import importlib
import json
import os
import traceback
from types import MappingProxyType
from typing import Any, NoReturn

import click

COMMANDS = MappingProxyType(
    {
        "completion": "astra.cli.completion",
        "guide": "astra.cli.guide",
        "rules": "astra.cli.rules",
        "schema": "astra.cli.schema",
        "spec": "astra.cli.spec",
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


def write_json(document: Any) -> None:
    """Print `document` as JSON, indented."""
    click.echo(json.dumps(document, indent=2, ensure_ascii=False))


main = click.version_option(package_name="astra-tools")(
    _Astra("astra", help="Validate ASTRA analyses, and read the specification's rules.")
)
