"""Command-line interface for ASTRA."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.tree import Tree

console = Console()


def _resolve_dir(directory: str | None) -> tuple[Path, str]:
    """Resolve a directory argument to an analysis path and format.

    Checks the given directory first, then walks up the tree via find_analysis_dir.
    """
    from astra.loader import find_analysis_dir

    dir_path = Path(directory) if directory else None
    try:
        return find_analysis_dir(dir_path)
    except FileNotFoundError:
        click.echo("Error: No astra.yaml or ro-crate-metadata.json found.", err=True)
        sys.exit(1)


def _load(directory: str | None) -> tuple[dict[str, Any], str]:
    """Load analysis data from a directory, detecting format."""
    path, fmt = _resolve_dir(directory)

    if fmt == "yaml":
        from astra.loader import load_yaml

        return load_yaml(path), fmt

    # Load RO-Crate and convert to dict-like structure for display
    return _rocrate_to_dict(path), fmt


def _rocrate_to_dict(path: Path) -> dict[str, Any]:
    """Load an RO-Crate and convert to a dict for display commands."""
    from astra.crate import ASTRACrate
    from astra.vocabulary import (
        PROP_INPUT_TYPE,
        PROP_OUTPUT_TYPE,
        SCHEMA_ALTERNATE_NAME,
        SCHEMA_DESCRIPTION,
        parse_entity_name,
    )

    crate = ASTRACrate.load(path)
    data: dict[str, Any] = {
        "name": crate.name,
        "description": crate.description,
        "astra_version": crate.astra_version,
        "inputs": [
            {
                "name": parse_entity_name(i.id),
                "type": i.get(PROP_INPUT_TYPE, ""),
                "description": i.get(SCHEMA_DESCRIPTION, ""),
            }
            for i in crate.get_inputs()
        ],
        "outputs": [
            {
                "name": parse_entity_name(o.id),
                "type": o.get(PROP_OUTPUT_TYPE, ""),
                "description": o.get(SCHEMA_DESCRIPTION, ""),
            }
            for o in crate.get_outputs()
        ],
        "decisions": {},
        "universes": {},
    }
    for dec in crate.get_decisions():
        dname = parse_entity_name(dec.id)
        opts = {}
        for opt in crate.get_options(dname):
            oname = parse_entity_name(opt.id)
            opts[oname] = {"name": oname, "label": opt.get(SCHEMA_ALTERNATE_NAME, "")}
        data["decisions"][dname] = {
            "name": dname,
            "label": dec.get(SCHEMA_ALTERNATE_NAME, ""),
            "options": opts,
        }
    for u in crate.get_universes():
        data["universes"][u.get("name", u.id)] = {
            "description": u.get(SCHEMA_DESCRIPTION, ""),
        }
    return data


@click.group()
@click.version_option(package_name="astra")
def main() -> None:
    """ASTRA - Agentic Schema for Transparent Research Analysis."""


@main.command()
@click.argument("directory", default=".")
def init(directory: str) -> None:
    """Create a new ASTRA analysis."""
    target = Path(directory)
    if (target / "astra.yaml").exists():
        click.echo(f"Error: {target / 'astra.yaml'} already exists.", err=True)
        sys.exit(1)

    analysis_name = target.resolve().name
    content = f"""\
name: {analysis_name}
astra_version: "1.0"
label: {analysis_name.replace("_", " ").title()}
description: A new ASTRA analysis.

inputs:
  - name: data
    type: data
    description: Input dataset

outputs:
  - name: result
    type: metric
    description: Analysis result
    recipe:
      command: python src/run.py

decisions:
  method:
    name: method
    label: Method
    default: a
    options:
      a:
        name: a
        label: Option A
      b:
        name: b
        label: Option B

universes:
  baseline:
    name: baseline
    description: Default configuration
    selections:
      - decision: method
        option: a
"""

    target.mkdir(parents=True, exist_ok=True)
    (target / "src").mkdir(exist_ok=True)
    (target / "outputs").mkdir(exist_ok=True)
    (target / "astra.yaml").write_text(content)

    gitignore = target / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("outputs/\n__pycache__/\n*.pyc\n.venv/\n")

    console.print(f"[green]Created ASTRA analysis in {target}/[/green]")


@main.command()
@click.argument("directory", required=False)
def validate(directory: str | None) -> None:
    """Validate an ASTRA analysis."""
    path, fmt = _resolve_dir(directory)

    if fmt == "yaml":
        from astra.loader import load_yaml, validate_yaml

        data = load_yaml(path)
        errors = validate_yaml(data)
        if errors:
            console.print(f"[red]Schema validation failed ({len(errors)} error(s)):[/red]")
            for e in errors:
                console.print(f"  [red]•[/red] {e}")
            sys.exit(1)
    else:
        from astra.crate import ASTRACrate
        from astra.validation.semantic import validate_analysis

        crate = ASTRACrate.load(path)
        errors = validate_analysis(crate)
        if errors:
            console.print(f"[red]Validation failed ({len(errors)} error(s)):[/red]")
            for e in errors:
                console.print(f"  [red]•[/red] {e}")
            sys.exit(1)

    console.print("[green]Validation passed.[/green]")


@main.command()
@click.option("-d", "--decisions", "show_decisions", is_flag=True)
@click.option("-i", "--inputs", "show_inputs", is_flag=True)
@click.option("-o", "--outputs", "show_outputs", is_flag=True)
@click.argument("directory", required=False)
def info(
    directory: str | None,
    show_decisions: bool,
    show_inputs: bool,
    show_outputs: bool,
) -> None:
    """Display analysis metadata."""
    data, _ = _load(directory)
    show_all = not (show_decisions or show_inputs or show_outputs)

    console.print(f"[bold]{data.get('label', data.get('name', ''))}[/bold]")
    if data.get("description"):
        console.print(f"  {data['description'].strip()}")
    console.print(f"  Version: {data.get('astra_version', '?')}")
    console.print()

    if show_all or show_inputs:
        console.print("[bold]Inputs:[/bold]")
        for inp in data.get("inputs") or []:
            console.print(f"  • {inp['name']} ({inp.get('type', '')}) {inp.get('description', '')}")
        console.print()

    if show_all or show_outputs:
        console.print("[bold]Outputs:[/bold]")
        for out in data.get("outputs") or []:
            console.print(f"  • {out['name']} ({out.get('type', '')}) {out.get('description', '')}")
        console.print()

    if show_all or show_decisions:
        console.print("[bold]Decisions:[/bold]")
        for dec_name, dec in (data.get("decisions") or {}).items():
            label = dec.get("label", "")
            console.print(f"  • {dec_name}: {label}")
            for opt_name in dec.get("options") or {}:
                console.print(f"    - {opt_name}")
        console.print()

    universes = data.get("universes") or {}
    if universes:
        console.print("[bold]Universes:[/bold]")
        for name, uni in universes.items():
            desc = uni.get("description", "")
            console.print(f"  • {name}: {desc}")


@main.group()
def universe() -> None:
    """Universe management commands."""


@universe.command("generate")
@click.option("-n", "--name", default="baseline", help="Universe name")
@click.option("-d", "--description", default=None, help="Description")
@click.argument("directory", required=False)
def universe_generate(name: str, description: str | None, directory: str | None) -> None:
    """Generate a default universe from analysis defaults."""
    from astra.helpers import generate_default_universe
    from astra.loader import load_yaml, save_yaml

    dir_path, _ = _resolve_dir(directory)
    data = load_yaml(dir_path)

    universes = data.setdefault("universes", {})
    if name in universes:
        click.echo(f"Error: Universe '{name}' already exists.", err=True)
        sys.exit(1)

    universe_data = generate_default_universe(data, name, description)
    universes[name] = universe_data
    save_yaml(data, dir_path / "astra.yaml")
    console.print(f"[green]Generated universe '{name}'[/green]")


@universe.command("check")
@click.argument("name")
@click.argument("directory", required=False)
def universe_check(name: str, directory: str | None) -> None:
    """Validate a universe against the analysis."""
    from astra.helpers import get_universe

    data, _ = _load(directory)
    u = get_universe(data, name)
    if not u:
        console.print(f"[red]Universe '{name}' not found.[/red]")
        sys.exit(1)
    console.print(f"[green]Universe '{name}' is valid.[/green]")


@main.command()
@click.argument("directory", required=False)
def viz(directory: str | None) -> None:
    """Visualize analysis structure as a tree."""
    data, _ = _load(directory)
    label = data.get("label", data.get("name", "Analysis"))
    tree = Tree(f"[bold]{label}[/bold]")
    _build_tree(tree, data)
    console.print(tree)


def _build_tree(tree: Tree, data: dict[str, Any]) -> None:
    """Recursively build a Rich tree from analysis data."""
    inputs = data.get("inputs") or []
    if inputs:
        branch = tree.add("[cyan]inputs[/cyan]")
        for inp in inputs:
            branch.add(f"{inp['name']} ({inp.get('type', '')})")

    outputs = data.get("outputs") or []
    if outputs:
        branch = tree.add("[green]outputs[/green]")
        for out in outputs:
            branch.add(f"{out['name']} ({out.get('type', '')})")

    decisions = data.get("decisions") or {}
    if decisions:
        branch = tree.add("[yellow]decisions[/yellow]")
        for dec_name, dec in decisions.items():
            label = dec.get("label", "")
            node = branch.add(f"{dec_name}: {label}")
            for opt_name in dec.get("options") or {}:
                node.add(opt_name)

    for sub_name, sub_data in (data.get("analyses") or {}).items():
        sub_branch = tree.add(f"[magenta]{sub_name}/[/magenta]")
        _build_tree(sub_branch, sub_data)


@main.group()
def export() -> None:
    """Export analysis to other formats."""


@export.command("rocrate")
@click.option("-o", "--output", default=None, help="Output directory")
@click.argument("directory", required=False)
def export_rocrate_cmd(output: str | None, directory: str | None) -> None:
    """Export analysis as RO-Crate."""
    from astra.export import export_rocrate
    from astra.loader import load_yaml, validate_yaml

    dir_path, _ = _resolve_dir(directory)
    data = load_yaml(dir_path)

    errors = validate_yaml(data)
    if errors:
        console.print("[red]Validation failed, cannot export:[/red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
        sys.exit(1)

    output_dir = Path(output) if output else dir_path
    export_rocrate(data, output_dir)
    console.print(f"[green]Exported RO-Crate to {output_dir}/[/green]")


@main.group()
def paper() -> None:
    """Paper management commands."""


@paper.command("add")
@click.argument("doi")
@click.option("--version", type=int, default=None, help="arXiv version")
@click.option("--pdf", type=click.Path(exists=True), default=None)
def paper_add(doi: str, version: int | None, pdf: str | None) -> None:
    """Download and cache a paper by DOI."""
    from astra.papers.download import download_paper_to_cache

    if pdf:
        from astra.papers.cache import PaperCache

        cache = PaperCache()
        cache.add_from_file(doi, Path(pdf), version=version)
        console.print(f"[green]Cached paper from {pdf}[/green]")
    else:
        _, result = download_paper_to_cache(doi, version=version)
        if result.success:
            console.print(f"[green]Downloaded and cached: {doi}[/green]")
            if result.title:
                console.print(f"  Title: {result.title}")
        else:
            console.print(f"[red]Failed to download: {result.error}[/red]")
            sys.exit(1)


@paper.command("list")
def paper_list() -> None:
    """List all cached papers."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    papers = cache.list_papers()
    if not papers:
        console.print("No papers cached.")
        return
    for p in papers:
        title = p.metadata.title or "Unknown title"
        console.print(f"  • {p.metadata.doi}: {title}")


@paper.command("show")
@click.argument("doi")
@click.option("--version", type=int, default=None)
def paper_show(doi: str, version: int | None) -> None:
    """Show paper metadata."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    p = cache.get(doi, version=version)
    if not p:
        console.print(f"[red]Paper not found: {doi}[/red]")
        sys.exit(1)
    console.print(json.dumps(p.metadata.to_json(), indent=2))


@paper.command("path")
@click.argument("doi")
@click.option("--version", type=int, default=None)
def paper_path(doi: str, version: int | None) -> None:
    """Get path to cached PDF."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    path = cache.get_path(doi, version=version)
    if path:
        click.echo(str(path))
    else:
        console.print(f"[red]Paper not found: {doi}[/red]")
        sys.exit(1)


@paper.command("remove")
@click.argument("doi")
@click.option("--version", type=int, default=None)
def paper_remove(doi: str, version: int | None) -> None:
    """Remove a paper from the cache."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    if cache.remove(doi, version=version):
        console.print(f"[green]Removed: {doi}[/green]")
    else:
        console.print(f"[red]Paper not found: {doi}[/red]")
        sys.exit(1)
