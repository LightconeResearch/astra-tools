"""Command-line interface for ASTRA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.tree import Tree

from astra.crate import ASTRACrate
from astra.vocabulary import (
    PROP_INPUT_TYPE,
    PROP_OUTPUT_TYPE,
    SCHEMA_ALTERNATE_NAME,
    SCHEMA_DESCRIPTION,
    SCHEMA_NAME,
    parse_entity_name,
)

console = Console()


def find_crate_dir(start: Path | None = None) -> Path:
    """Find the nearest directory containing ro-crate-metadata.json."""
    current = start or Path.cwd()
    while True:
        if (current / "ro-crate-metadata.json").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    click.echo("Error: No ro-crate-metadata.json found in current or parent directories.", err=True)
    sys.exit(1)


@click.group()
@click.version_option(package_name="astra")
def main() -> None:
    """ASTRA - Agentic Schema for Transparent Research Analysis."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@main.command()
@click.argument("directory", default=".")
def init(directory: str) -> None:
    """Create a new ASTRA analysis (RO-Crate)."""
    target = Path(directory)
    if (target / "ro-crate-metadata.json").exists():
        click.echo(f"Error: {target / 'ro-crate-metadata.json'} already exists.", err=True)
        sys.exit(1)

    crate = ASTRACrate(
        name=target.resolve().name,
        version="1.0",
        description="A new ASTRA analysis.",
    )
    crate.add_input("data", "data", description="Input dataset")
    crate.add_output("result", "metric", description="Analysis result")
    crate.add_decision(
        "method",
        "Method",
        {"a": {"label": "Option A"}, "b": {"label": "Option B"}},
        default="a",
    )
    crate.generate_default_universe("baseline", description="Default configuration")

    target.mkdir(parents=True, exist_ok=True)
    (target / "src").mkdir(exist_ok=True)
    (target / "outputs").mkdir(exist_ok=True)

    gitignore = target / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("outputs/\n__pycache__/\n*.pyc\n.venv/\n")

    crate.write(target)
    console.print(f"[green]Created ASTRA analysis in {target}/[/green]")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@main.command()
@click.argument("directory", required=False)
def validate(directory: str | None) -> None:
    """Validate an ASTRA crate."""
    from astra.validation.semantic import validate_analysis

    crate_dir = Path(directory) if directory else find_crate_dir()
    crate = ASTRACrate.load(crate_dir)
    errors = validate_analysis(crate)

    if errors:
        console.print(f"[red]Validation failed with {len(errors)} error(s):[/red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
        sys.exit(1)
    else:
        console.print("[green]Validation passed.[/green]")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@main.command()
@click.option("-d", "--decisions", "show_decisions", is_flag=True, help="Show decisions")
@click.option("-i", "--inputs", "show_inputs", is_flag=True, help="Show inputs")
@click.option("-o", "--outputs", "show_outputs", is_flag=True, help="Show outputs")
@click.argument("directory", required=False)
def info(
    directory: str | None,
    show_decisions: bool,
    show_inputs: bool,
    show_outputs: bool,
) -> None:
    """Display analysis metadata."""
    crate_dir = Path(directory) if directory else find_crate_dir()
    crate = ASTRACrate.load(crate_dir)
    show_all = not (show_decisions or show_inputs or show_outputs)

    console.print(f"[bold]{crate.name}[/bold]")
    if crate.description:
        console.print(f"  {crate.description}")
    console.print(f"  Version: {crate.astra_version}")
    console.print()

    if show_all or show_inputs:
        console.print("[bold]Inputs:[/bold]")
        for inp in crate.get_inputs():
            name = parse_entity_name(inp.id)
            itype = inp.get(PROP_INPUT_TYPE, "")
            desc = inp.get(SCHEMA_DESCRIPTION, "")
            console.print(f"  • {name} ({itype}) {desc}")
        console.print()

    if show_all or show_outputs:
        console.print("[bold]Outputs:[/bold]")
        for out in crate.get_outputs():
            name = parse_entity_name(out.id)
            otype = out.get(PROP_OUTPUT_TYPE, "")
            desc = out.get(SCHEMA_DESCRIPTION, "")
            console.print(f"  • {name} ({otype}) {desc}")
        console.print()

    if show_all or show_decisions:
        console.print("[bold]Decisions:[/bold]")
        for dec in crate.get_decisions():
            name = parse_entity_name(dec.id)
            label = dec.get(SCHEMA_ALTERNATE_NAME, "")
            opts = crate.get_options(name)
            console.print(f"  • {name}: {label}")
            for opt in opts:
                console.print(f"    - {parse_entity_name(opt.id)}")
        console.print()

    universes = crate.get_universes()
    if universes:
        console.print("[bold]Universes:[/bold]")
        for u in universes:
            console.print(f"  • {u.get(SCHEMA_NAME, u.id)}: {u.get(SCHEMA_DESCRIPTION, '')}")


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------


@main.group()
def universe() -> None:
    """Universe management commands."""


@universe.command("generate")
@click.option("-n", "--name", default="baseline", help="Universe name")
@click.option("-d", "--description", default=None, help="Description")
@click.argument("directory", required=False)
def universe_generate(name: str, description: str | None, directory: str | None) -> None:
    """Generate a default universe from analysis defaults."""
    crate_dir = Path(directory) if directory else find_crate_dir()
    crate = ASTRACrate.load(crate_dir)

    if crate.get_universe(name):
        click.echo(f"Error: Universe '{name}' already exists.", err=True)
        sys.exit(1)

    crate.generate_default_universe(name, description=description)
    crate.write(crate_dir)
    console.print(f"[green]Generated universe '{name}'[/green]")


@universe.command("check")
@click.argument("name")
@click.argument("directory", required=False)
def universe_check(name: str, directory: str | None) -> None:
    """Validate a universe against the analysis."""
    from astra.validation.semantic import validate_universe

    crate_dir = Path(directory) if directory else find_crate_dir()
    crate = ASTRACrate.load(crate_dir)
    errors = validate_universe(name, crate)

    if errors:
        console.print(f"[red]Universe '{name}' has {len(errors)} error(s):[/red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
        sys.exit(1)
    else:
        console.print(f"[green]Universe '{name}' is valid.[/green]")


# ---------------------------------------------------------------------------
# viz
# ---------------------------------------------------------------------------


@main.command()
@click.argument("directory", required=False)
def viz(directory: str | None) -> None:
    """Visualize analysis structure as a tree."""
    crate_dir = Path(directory) if directory else find_crate_dir()
    crate = ASTRACrate.load(crate_dir)

    tree = Tree(f"[bold]{crate.name}[/bold]")
    _build_tree(tree, crate, crate_dir)
    console.print(tree)


def _build_tree(tree: Tree, crate: ASTRACrate, crate_dir: Path) -> None:
    """Recursively build a Rich tree from an ASTRA crate."""
    inputs = crate.get_inputs()
    if inputs:
        inp_branch = tree.add("[cyan]inputs[/cyan]")
        for inp in inputs:
            name = parse_entity_name(inp.id)
            inp_branch.add(f"{name} ({inp.get(PROP_INPUT_TYPE, '')})")

    outputs = crate.get_outputs()
    if outputs:
        out_branch = tree.add("[green]outputs[/green]")
        for out in outputs:
            name = parse_entity_name(out.id)
            out_branch.add(f"{name} ({out.get(PROP_OUTPUT_TYPE, '')})")

    decisions = crate.get_decisions()
    if decisions:
        dec_branch = tree.add("[yellow]decisions[/yellow]")
        for dec in decisions:
            name = parse_entity_name(dec.id)
            opts = crate.get_options(name)
            dec_node = dec_branch.add(f"{name}: {dec.get(SCHEMA_ALTERNATE_NAME, '')}")
            for opt in opts:
                dec_node.add(parse_entity_name(opt.id))

    # Subcrate directories
    for sub_name in sorted(crate_dir.iterdir()):
        if sub_name.is_dir() and (sub_name / "ro-crate-metadata.json").exists():
            sub_crate = ASTRACrate.load(sub_name)
            sub_branch = tree.add(f"[magenta]{sub_name.name}/[/magenta]")
            _build_tree(sub_branch, sub_crate, sub_name)


# ---------------------------------------------------------------------------
# paper commands (preserved from v1)
# ---------------------------------------------------------------------------


@main.group()
def paper() -> None:
    """Paper management commands."""


@paper.command("add")
@click.argument("doi")
@click.option("--version", type=int, default=None, help="arXiv version")
@click.option("--pdf", type=click.Path(exists=True), default=None, help="Local PDF file")
def paper_add(doi: str, version: int | None, pdf: str | None) -> None:
    """Download and cache a paper by DOI."""
    from astra.papers.download import download_paper_to_cache

    if pdf:
        from astra.papers.cache import PaperCache

        cache = PaperCache()
        cache.add_from_file(doi, Path(pdf), version=version)
        console.print(f"[green]Cached paper from {pdf}[/green]")
    else:
        path, result = download_paper_to_cache(doi, version=version)
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
