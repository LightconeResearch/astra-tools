"""`astra guide`: the guide for agents, `llms.txt`, as astra-spec ships it."""

from __future__ import annotations

from importlib.resources import files

import click


@click.command("guide")
def command() -> None:
    """Print the ASTRA guide for agents (llms.txt).

    It is astra-spec's own file, unchanged.
    """
    data = (files("astra") / "docs" / "llms.txt").read_bytes()
    click.echo(data, nl=False)
