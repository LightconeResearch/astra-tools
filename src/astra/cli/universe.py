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
    show_universes(stack.analysis(stack.root))  # OPEN(O22): text alone


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
    from astra.stack import Element

    stack = read_stack(path)
    analysis = stack.analysis(stack.root)  # read_stack gives a stack whose root's file is valid
    entry = analysis.universes.get(universe)
    if entry is None or entry.is_import:
        own = [id_ for id_, u in analysis.universes.items() if not u.is_import]
        listed = ", ".join(own) if own else "none"
        what = (
            f"`{universe}` is an import, which selects nothing"
            if entry
            else f"the analysis has no universe `{universe}`"
        )
        raise click.BadParameter(f"{what}: its universes are {listed}", param_hint="UNIVERSE")
    found = universes.selections(stack, universes.written(stack))
    selection = found[Element(stack.root, "universe", universe)]
    if selection is None:  # Annex D case 7; OPEN(O23)
        click.echo(
            f"astra: `{universe}` has no effective selection, since its `derived_from` names no "
            "universe of the analysis, or its chain loops or reaches one that has none: "
            "`astra validate` says where",
            err=True,
        )
        raise click.exceptions.Exit(FAILED)
    show_selection(selection, entry.derived_from)  # OPEN(O22): text alone
