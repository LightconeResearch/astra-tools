"""The stack in brief, as text: each analysis, the root first, with its file, its label, and
its declarations, inputs, outputs and switches, decisions and universes, or only those rows
asked for."""

from __future__ import annotations

from rich.text import Text

from astra import model
from astra.cli.text import console, file_named
from astra.stack import Declaration, Stack


def show(stack: Stack, only: set[str] | None = None) -> None:
    """Each analysis of `stack`, with every row, or only the rows `only` names."""
    out = console()
    for member in stack.analyses.values():
        heading = Text(file_named(stack.location(member.identity, ())), style="bold")
        analysis = member.analysis
        if analysis is not None and analysis.label is not None:
            heading.append(f"  {analysis.label}")
        out.print(heading)
        if analysis is None:
            out.print("  not a valid document: `astra validate` says why")
            continue
        rows = {
            "analyses": [
                f"{id_}: {_reached(stack, declaration)}"
                for id_, declaration in member.declarations.items()
            ],
            "inputs": [f"{id_}: {input_.path}" for id_, input_ in analysis.inputs.items()],
            "outputs": [_output(id_, o) for id_, o in analysis.outputs.items()],
            "decisions": [
                f"{id_}: {', '.join(decision.options)}"
                for id_, decision in analysis.decisions.items()
            ],
            "universes": [_universe(id_, u) for id_, u in analysis.universes.items()],
        }
        for name, items in rows.items():
            if only is not None and name not in only:
                continue
            for index, item in enumerate(items):
                out.print(Text.assemble("  ", (f"{name if index == 0 else '':<10}", "bold"), item))


def _reached(stack: Stack, declaration: Declaration) -> str:
    """The analysis a declaration reaches, by its file, or why it reaches none."""
    if declaration.reached is None:
        return f"nothing ({declaration.outcome})"
    file = file_named(stack.location(declaration.reached, ()))
    return f"{file} (not a valid document)" if declaration.outcome == "invalid" else file


def _output(id_: str, output: model.Output) -> str:
    """An output's type and format; a switch's decision and cases (Elements *switch*)."""
    if output.is_switch:
        cases = ", ".join(f"{option}: {target}" for option, target in output.cases.items())
        return f"{id_}: switch on {output.switch} ({cases})"
    return f"{id_}: {output.type}, {output.format}"


def _universe(id_: str, universe: model.Universe) -> str:
    if universe.is_import:
        return f"{id_}: imports {universe.analysis}.{universe.universe}"
    if universe.derived_from is not None:
        return f"{id_}: derived from {universe.derived_from}"
    return id_
