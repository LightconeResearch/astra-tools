"""An analysis in brief, as text: its label and description, its inputs, outputs, decisions
(those of the analyses it declares after its own) and universes, or only the parts asked for."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from astra import model
from astra.cli.text import console
from astra.stack import Identity, Stack


def show(stack: Stack, only: set[str] | None = None) -> None:
    """The root analysis of `stack`, with every part, or only the parts `only` names."""
    out = console()
    analysis = stack.analysis(stack.root)
    out.print(f"[bold]{escape(analysis.label or 'Unknown')}[/bold]")
    out.print(f"Spec version: {escape(analysis.spec_version)}")
    if analysis.description and analysis.description.strip():
        out.print()
        out.print(escape(analysis.description.strip()))
    out.print(
        f"\n[dim]Inputs: {len(analysis.inputs)} | Outputs: {len(analysis.outputs)} | "
        f"Decisions: {len(analysis.decisions)} | Universes: {len(analysis.universes)}[/dim]"
    )
    layout = _layout(stack)
    if layout:
        out.print(f"[dim]Layout: {escape(layout)}[/dim]")

    def asked(part: str) -> bool:
        return only is None or part in only

    if asked("inputs"):
        out.print("\n[bold]Inputs:[/bold]")
        table = Table(show_header=True)
        for column in ("ID", "Path", "Description"):
            table.add_column(column)
        for id_, input_ in analysis.inputs.items():
            table.add_row(id_, escape(input_.path), escape(input_.description or ""))
        out.print(table)
    if asked("outputs"):
        out.print("\n[bold]Outputs:[/bold]")
        table = Table(show_header=True)
        for column in ("ID", "Type", "Recipe", "Description"):
            table.add_column(column)
        for id_, output in analysis.outputs.items():
            table.add_row(id_, *_output(output), escape(output.description or ""))
        out.print(table)
    if asked("decisions"):
        out.print("\n[bold]Decisions:[/bold]")
        _decisions(out, analysis)
        _declared(out, stack, stack.root, {stack.root}, 0)
    if only is None and analysis.universes:
        out.print("\n[bold]Universes:[/bold]")
        for id_, universe in analysis.universes.items():
            out.print(f"  [cyan]{id_}[/cyan]{escape(_universe(universe))}")


def _layout(stack: Stack) -> str:
    """One line on the analyses the root declares, with the folders of those in its tree."""
    declarations = stack.analyses[stack.root].declarations
    if not declarations:
        return ""
    folders = sorted(
        f"./{declaration.folder}/"
        for declaration in declarations.values()
        if declaration.declared.path is not None and declaration.folder
    )
    noun = "sub-analysis" if len(declarations) == 1 else "sub-analyses"
    if len(folders) == len(declarations):
        return f"{len(declarations)} {noun} in {', '.join(folders)}"
    if folders:
        return f"{len(declarations)} {noun} ({len(folders)} in {', '.join(folders)})"
    return f"{len(declarations)} {noun}"


def _output(output: model.Output) -> tuple[str, str]:
    """An output's type and its recipe's command; a switch's decision and cases."""
    if output.is_switch:
        cases = ", ".join(f"{option}: {target}" for option, target in output.cases.items())
        return "switch", escape(f"on {output.switch} ({cases})")
    command = "[dim]-[/dim]" if output.recipe is None else escape(output.recipe.command)
    return escape(output.type or ""), command


def _universe(universe: model.Universe) -> str:
    if universe.is_import:
        return f": imports {universe.analysis}.{universe.universe}"
    if universe.derived_from is not None:
        return f": derived from {universe.derived_from}"
    return ""


def _decisions(out: Console, analysis: model.Analysis, indent: str = "") -> None:
    """Each decision of `analysis`, as a tree of its rationale and options."""
    for id_, decision in analysis.decisions.items():
        tree = Tree(f"{indent}[cyan]{id_}[/cyan]: {escape(decision.label or '')}")
        if decision.tags:
            tree.add(f"[dim]Tags:[/dim] {escape(', '.join(decision.tags))}")
        if decision.rationale:
            tree.add(f"[dim]Rationale:[/dim] {escape(decision.rationale)}")
        options = tree.add("[dim]Options:[/dim]")
        for option_id, option in decision.options.items():
            text = f"{option_id}: {escape(option.label or '')}"
            if option.excluded is not None:
                text += f" [yellow](excluded: {escape(option.excluded)})[/yellow]"
            if option.description:
                text += f" - [dim]{escape(option.description)}[/dim]"
            options.add(text)
        out.print(tree)
        out.print()


def _declared(out: Console, stack: Stack, owner: Identity, seen: set[Identity], depth: int) -> None:
    """The decisions of each analysis `owner` declares, and of those they declare, once each."""
    for id_, declaration in stack.analyses[owner].declarations.items():
        reached = declaration.reached
        if reached is None or reached in seen:
            continue
        seen.add(reached)
        out.print(f"\n  [bold magenta]{'  ' * depth}Analysis: {id_}[/bold magenta]")
        analysis = stack.analyses[reached].analysis
        if analysis is not None:
            _decisions(out, analysis, "  " * (depth + 1))
        _declared(out, stack, reached, seen, depth + 1)
