"""`astra universe list|show U [PATH]`: the root's universes, and one universe's effective
selection (§12, design §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, read_stack


@click.group("universe")
def command() -> None:
    """Show the universes of an analysis.

    PATH is the analysis's folder, the current one by default.
    """


@command.command("list")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def list_(path: Path | None) -> None:
    """List the universes and imports of the analysis in PATH."""
    from astra.cli.text.universe import show_universes

    stack = read_stack(path)
    show_universes(stack.analysis(stack.root))  # text alone


@command.command("show")
@click.argument("universe")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def show(universe: str, path: Path | None) -> None:
    """Show the effective selection of UNIVERSE, one of the universes of the analysis in PATH.

    It is what the universe selects once its derived_from is resolved (§12): each decision,
    with the option selected and, where it is inherited, the universe it comes from. Exits 1
    where the universe has no effective selection.
    """
    from astra import universes
    from astra.cli.text.universe import show_selection
    from astra.plan import RequestError, root_universe

    stack = read_stack(path)
    try:
        element = root_universe(stack, universe)
    except RequestError as error:
        raise click.BadParameter(str(error), param_hint="UNIVERSE") from None
    found = universes.selections(stack)
    selection = found[element]
    if selection is None:  # design §4.13 case 7
        click.echo(
            f"astra: `{universe}` has no effective selection, since its `derived_from` names no "
            "universe of the analysis, or its chain loops or reaches one that has none: "
            "`astra validate` says where",
            err=True,
        )
        raise click.exceptions.Exit(FAILED)
    derived_from = stack.analysis(stack.root).universes[universe].derived_from
    show_selection(selection, derived_from)  # text alone
