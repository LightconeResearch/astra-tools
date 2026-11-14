"""`astra info [-f FILE] [-d] [-i] [-o] [--json]`: an analysis in brief."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from astra.cli import FAILED, find_analysis, read_stack, write_json

if TYPE_CHECKING:
    from astra import model
    from astra.stack import Member, Stack

SHAPE = "astra-info/1"
"""The JSON of `info --json`."""


@click.command("info")
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file (default: astra.yaml in current/parent dir)",
)
@click.option("--decisions", "-d", is_flag=True, help="Show decision details")
@click.option("--inputs", "-i", is_flag=True, help="Show input details")
@click.option("--outputs", "-o", is_flag=True, help="Show output details")
@click.option("--json", "as_json", is_flag=True, help="Print the information as JSON.")
def command(file: Path | None, decisions: bool, inputs: bool, outputs: bool, as_json: bool) -> None:
    """Show information about an analysis.

    Its label and description, then its inputs, outputs, decisions (those of the analyses it
    declares after its own) and universes; with -d, -i or -o, only those asked for. It checks
    nothing: `astra validate` does. With --json, every analysis of the stack is printed as
    JSON (`astra-info/1`), the root first. Exits 1 where there is no analysis, or no stack to
    show.
    """
    found = find_analysis() if file is None else file
    if found is None:
        click.echo("Error: No astra.yaml found in current directory or parents.", err=True)
        click.echo("Use --file to specify the analysis file.", err=True)
        raise click.exceptions.Exit(FAILED)
    stack = read_stack(found if found.is_dir() else found.parent)
    if as_json:
        write_json(to_json(stack))
        return
    asked = {
        name
        for name, wanted in (("decisions", decisions), ("inputs", inputs), ("outputs", outputs))
        if wanted
    }
    from astra.cli.text.info import show

    show(stack, asked or None)


def to_json(stack: Stack) -> dict[str, Any]:
    """The stack as `astra-info/1`: each analysis, the root first."""
    return {
        "shape": SHAPE,
        "analyses": [_member(stack, member) for member in stack.analyses.values()],
    }


def _member(stack: Stack, member: Member) -> dict[str, Any]:
    document: dict[str, Any] = {
        "file": member.file,
        "commit": member.identity.commit,
        "url": member.url,
        "valid": member.analysis is not None,
    }
    analysis = member.analysis
    if analysis is None:
        return document
    declared = {}
    for id_, declaration in member.declarations.items():
        reached = declaration.reached
        declared[id_] = None if reached is None else stack.analyses[reached].file
    return {
        **document,
        "spec_version": analysis.spec_version,
        "label": analysis.label,
        "description": analysis.description,
        "analyses": declared,
        "inputs": {
            id_: {"path": input_.path, "description": input_.description}
            for id_, input_ in analysis.inputs.items()
        },
        "outputs": {id_: _output(output) for id_, output in analysis.outputs.items()},
        "decisions": {
            id_: {
                "label": decision.label,
                "rationale": decision.rationale,
                "options": {
                    option_id: {
                        "label": option.label,
                        "description": option.description,
                        "excluded": option.excluded,
                    }
                    for option_id, option in decision.options.items()
                },
            }
            for id_, decision in analysis.decisions.items()
        },
        "universes": {id_: _universe(universe) for id_, universe in analysis.universes.items()},
    }


def _output(output: model.Output) -> dict[str, Any]:
    if output.is_switch:
        return {"switch": output.switch, "cases": dict(output.cases)}
    return {
        "type": output.type,
        "format": output.format,
        "command": None if output.recipe is None else output.recipe.command,
        "inputs": list(output.inputs),
        "decisions": list(output.decisions),
        "description": output.description,
    }


def _universe(universe: model.Universe) -> dict[str, Any]:
    if universe.is_import:
        return {"analysis": universe.analysis, "universe": universe.universe}
    return {
        "label": universe.label,
        "derived_from": universe.derived_from,
        "decisions": dict(universe.decisions),
    }
