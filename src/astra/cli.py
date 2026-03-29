"""Command-line interface for ASTRA."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from astra.helpers import (
    _collect_node_decisions,
    create_universe_from_defaults,
    get_analysis_decisions,
    get_decisions,
    get_inputs,
    get_outputs,
    load_yaml,
    save_yaml,
)
from astra.validation.schema import (
    get_analysis_schema,
    get_insights_schema,
    get_universe_schema,
    validate_analysis_schema,
    validate_universe_schema,
)
from astra.validation.semantic import validate_analysis_file, validate_universe_file

console = Console()


def find_analysis_file(start_path: Path | None = None) -> Path | None:
    """Find the astra.yaml file in the current or parent directories."""
    if start_path is None:
        start_path = Path.cwd()

    # Resolve to absolute path to ensure parent traversal works correctly
    current = start_path.resolve()
    while current != current.parent:
        astra_file = current / "astra.yaml"
        if astra_file.exists():
            return astra_file
        current = current.parent

    return None


def _require_analysis(analysis: Path | None, start_path: Path | None = None) -> Path:
    """Find or validate analysis file, exit with error if not found."""
    if analysis is not None:
        return analysis
    found = find_analysis_file(start_path)
    if found is None:
        console.print("[red]Error:[/red] No astra.yaml found.")
        raise SystemExit(1)
    return found


@click.group()
@click.version_option()
def main() -> None:
    """ASTRA - Agentic Schema for Transparent Research Analysis CLI."""
    pass


@main.command()
@click.argument("directory", type=click.Path(path_type=Path), default=".")
@click.option("--no-git", is_flag=True, help="Don't initialize git repository")
def init(directory: Path, no_git: bool) -> None:
    """Create a minimal ASTRA analysis scaffold.

    Creates astra.yaml, universes/baseline.yaml, and .gitignore.

    DIRECTORY is the project folder to create (default: current directory).

    For full agentic scaffolding (Claude Code config, venv, HPC),
    use 'prism init' instead.

    Examples:
        astra init my-analysis
        astra init my-analysis --no-git
    """
    # Check if this is already an ASTRA project
    if (directory / "astra.yaml").exists():
        console.print(
            f"[red]Error:[/red] [cyan]{directory}[/cyan] is already an ASTRA project "
            f"(astra.yaml exists)."
        )
        console.print(
            "Use [cyan]astra validate[/cyan] to check it, or delete astra.yaml to re-init."
        )
        raise SystemExit(1)

    # Create project directory
    if directory != Path("."):
        if directory.exists() and any(directory.iterdir()):
            console.print(
                f"[red]Error:[/red] [cyan]{directory}[/cyan] already exists and is not empty. "
                "Please specify an empty or non-existing directory."
            )
            raise SystemExit(1)
        directory.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    (directory / "universes").mkdir(parents=True, exist_ok=True)
    (directory / "outputs").mkdir(parents=True, exist_ok=True)
    (directory / "src").mkdir(parents=True, exist_ok=True)

    # Create .gitignore
    gitignore = """# ASTRA Analysis
outputs/
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
.DS_Store
"""
    (directory / ".gitignore").write_text(gitignore)

    # Create boilerplate astra.yaml
    _create_boilerplate_astra_yaml(directory)

    # Initialize git repository
    _init_git_repo(directory, no_git)

    # Print success message
    console.print(f"[green]✓[/green] Created ASTRA analysis scaffold: [cyan]{directory}[/cyan]")
    console.print("\nFor full agentic scaffolding, use [cyan]prism init[/cyan] instead.")


def _create_boilerplate_astra_yaml(directory: Path) -> None:
    """Create boilerplate astra.yaml with TODOs."""
    name = directory.name if directory != Path(".") else "My Analysis"

    astra_yaml = f"""# ASTRA Analysis Specification
# Documentation: https://github.com/LightconeResearch/ASTRA

version: "1.0"
name: "{name}"
description: |
  TODO: Describe the goal of this analysis.

inputs:
  - id: primary_data
    type: data
    description: "TODO: Describe your primary data source"

outputs:
  - id: main_result
    type: metric
    description: "TODO: Describe your primary output metric"
    recipe:
      command: python src/main.py

  - id: conclusion
    type: report
    description: "Summary of analysis findings"
    recipe:
      command: python src/main.py
      inputs: [main_result]

decisions:
  example_method:
    label: "Example Method Choice"
    rationale: "TODO: Explain why this decision matters"
    default: option_a
    options:
      option_a:
        label: "Option A"
        description: "TODO: Describe option A"
      option_b:
        label: "Option B"
        description: "TODO: Describe option B"
"""
    (directory / "astra.yaml").write_text(astra_yaml)

    # Create baseline universe
    baseline_universe = """# Baseline Universe
# Default configuration using standard practices

id: baseline
description: "Default configuration using standard practices"

decisions:
  example_method: option_a
"""
    (directory / "universes" / "baseline.yaml").write_text(baseline_universe)


def _init_git_repo(directory: Path, no_git: bool) -> None:
    """Initialize git repository if requested."""
    if no_git or (directory / ".git").exists():
        return

    try:
        subprocess.run(
            ["git", "init"],
            cwd=directory,
            capture_output=True,
            check=True,
        )
        console.print("[green]✓[/green] Initialized git repository")
        # Try to create initial commit
        try:
            subprocess.run(["git", "add", "."], cwd=directory, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial ASTRA analysis structure"],
                cwd=directory,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            pass  # Commit failed, but repo is initialized
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Git not available


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--analysis",
    "-a",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file for universe validation",
)
@click.option(
    "--verify-evidence",
    "-e",
    is_flag=True,
    help="Verify evidence quotes exist in source papers (requires papers to be cached)",
)
@click.option(
    "--skip-evidence",
    is_flag=True,
    help="Skip evidence verification even if insights are present",
)
def validate(file: Path, analysis: Path | None, verify_evidence: bool, skip_evidence: bool) -> None:
    """Validate an ASTRA specification file.

    FILE can be an analysis (astra.yaml) or universe file.
    For universe files, use --analysis to specify the analysis file.

    Evidence verification (--verify-evidence) checks that quotes in insights
    actually exist in the source papers. Papers must be cached first using
    'astra paper add'.
    """
    # Determine file type
    is_universe = "universe" in file.stem.lower() or file.parent.name == "universes"

    if is_universe and analysis is None:
        # Try to find analysis file
        analysis = find_analysis_file(file.parent)
        if analysis is None:
            console.print("[red]Error:[/red] Universe validation requires an analysis file.")
            console.print("Use --analysis to specify the analysis file.")
            raise SystemExit(1)

    console.print(f"Validating [cyan]{file}[/cyan]...")

    # Schema validation
    if is_universe:
        schema_errors = validate_universe_schema(file)
    else:
        schema_errors = validate_analysis_schema(file)

    if schema_errors:
        console.print("\n[red]Schema validation errors:[/red]")
        for schema_err in schema_errors:
            console.print(f"  • {schema_err}")
        raise SystemExit(1)

    console.print("[green]✓[/green] Schema validation passed")

    # Semantic validation
    if is_universe:
        assert analysis is not None
        semantic_errors = validate_universe_file(file, analysis)
    else:
        semantic_errors = validate_analysis_file(file)

    if semantic_errors:
        console.print("\n[red]Semantic validation errors:[/red]")
        for semantic_err in semantic_errors:
            console.print(f"  • {semantic_err}")
        raise SystemExit(1)

    console.print("[green]✓[/green] Semantic validation passed")

    # Evidence verification (for analysis files with insights)
    if not is_universe and not skip_evidence:
        data = load_yaml(file)
        insights = data.get("insights", {})

        if insights:
            if not verify_evidence:
                # Show hint about evidence verification
                evidence_count = sum(
                    len(insight.get("evidence", [])) for insight in insights.values()
                )
                if evidence_count > 0:
                    console.print(
                        f"\n[dim]Note: {len(insights)} insight(s) with {evidence_count} "
                        f"evidence item(s) found.[/dim]"
                    )
                    console.print(
                        "[dim]Run with --verify-evidence to verify quotes exist in papers.[/dim]"
                    )
            else:
                console.print("\n[bold]Verifying evidence...[/bold]")
                _verify_insights_evidence(insights)

    console.print("\n[green]Validation successful![/green]")


def _verify_insights_evidence(insights: dict[str, Any]) -> None:
    """Verify evidence for all insights."""
    from astra.papers.cache import PaperCache
    from astra.verification.cache import VerificationCache
    from astra.verification.core import VerificationStatus, verify_all_insights

    paper_cache = PaperCache()
    verification_cache = VerificationCache()

    results = verify_all_insights(insights, paper_cache, verification_cache)

    has_errors = False
    verified_count = 0
    cached_count = 0
    skipped_count = 0
    failed_count = 0

    for insight_id, result in results.items():
        for ev_result in result.evidence_results:
            status = ev_result.status
            if status in (VerificationStatus.VERIFIED, VerificationStatus.CACHED):
                verified_count += 1
                if status == VerificationStatus.CACHED:
                    cached_count += 1
            elif status == VerificationStatus.SKIPPED:
                skipped_count += 1
            else:
                failed_count += 1
                has_errors = True
                if status == VerificationStatus.ERROR:
                    icon = "[yellow]![/yellow]"
                else:
                    icon = "[red]✗[/red]"
                console.print(
                    f"  {icon} [{insight_id}] {ev_result.evidence_id}: {ev_result.message}"
                )

    # Summary
    total = verified_count + skipped_count + failed_count
    if cached_count > 0:
        console.print(
            f"[green]✓[/green] Evidence: {verified_count}/{total} verified "
            f"({cached_count} from cache), {skipped_count} skipped"
        )
    else:
        console.print(
            f"[green]✓[/green] Evidence: {verified_count}/{total} verified, {skipped_count} skipped"
        )

    if has_errors:
        console.print(f"\n[red]Error:[/red] {failed_count} evidence item(s) failed verification")
        console.print("\nTo fix:")
        console.print("  1. Check that quotes are exact copies from the paper")
        console.print("  2. Verify the DOI and version are correct")
        console.print("  3. Ensure the paper is cached: astra paper add <doi>")
        raise SystemExit(1)


@main.command()
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file (default: astra.yaml in current/parent dir)",
)
@click.option("--decisions", "-d", is_flag=True, help="Show decision details")
@click.option("--inputs", "-i", is_flag=True, help="Show input details")
@click.option("--outputs", "-o", is_flag=True, help="Show output details")
def info(
    file: Path | None,
    decisions: bool,
    inputs: bool,
    outputs: bool,
) -> None:
    """Show information about an analysis."""
    file = _require_analysis(file)
    data = load_yaml(file)

    # Header
    console.print(f"\n[bold]{data.get('name', 'Unknown')}[/bold]")
    console.print(f"Version: {data.get('version', 'Unknown')}")
    if data.get("description"):
        console.print(f"\n{data['description']}")

    # Summary stats
    input_list = get_inputs(data)
    output_list = get_outputs(data)
    decision_dict = get_decisions(data)
    console.print(
        f"\n[dim]Inputs: {len(input_list)} | "
        f"Outputs: {len(output_list)} | "
        f"Decisions: {len(decision_dict)}[/dim]"
    )

    # Show all by default if no flags
    show_all = not (decisions or inputs or outputs)

    # Inputs
    if inputs or show_all:
        console.print("\n[bold]Inputs:[/bold]")
        table = Table(show_header=True)
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Description")

        for inp in input_list:
            table.add_row(inp.get("id", ""), inp.get("type", ""), inp.get("description", ""))
        console.print(table)

    # Outputs
    if outputs or show_all:
        console.print("\n[bold]Outputs:[/bold]")
        table = Table(show_header=True)
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Recipe")
        table.add_column("Description")

        for out in output_list:
            recipe = out.get("recipe")
            if recipe:
                recipe_str = recipe.get("command", "yes")
            else:
                recipe_str = "[dim]-[/dim]"
            table.add_row(
                out.get("id", ""),
                out.get("type", ""),
                recipe_str,
                out.get("description", ""),
            )
        console.print(table)

    # Decisions (recursive tree)
    if decisions or show_all:
        console.print("\n[bold]Decisions:[/bold]")
        decision_tree = get_analysis_decisions(data)
        _display_decisions(decision_tree.get("decisions", {}))
        _display_analysis_decisions(decision_tree.get("analyses", {}))


def _display_decisions(decisions: dict[str, Any], indent: str = "") -> None:
    """Display decisions as Rich trees."""
    for decision_id, decision in decisions.items():
        tree = Tree(f"{indent}[cyan]{decision_id}[/cyan]: {decision.get('label', '')}")
        tags = decision.get("tags") or []
        if tags:
            tree.add(f"[dim]Tags:[/dim] {', '.join(tags)}")
        if decision.get("rationale"):
            tree.add(f"[dim]Rationale:[/dim] {decision['rationale']}")

        options_branch = tree.add("[dim]Options:[/dim]")
        options = decision.get("options", {})
        default = decision.get("default")
        for option_id, option in options.items():
            default_marker = " [yellow](default)[/yellow]" if option_id == default else ""
            option_text = f"{option_id}: {option.get('label', '')}{default_marker}"
            if option.get("description"):
                option_text += f" - [dim]{option['description']}[/dim]"
            options_branch.add(option_text)

        console.print(tree)
        console.print()


def _display_analysis_decisions(analyses: dict[str, Any], depth: int = 0) -> None:
    """Recursively display decisions grouped by sub-analysis."""
    for analysis_id, analysis_tree in analyses.items():
        console.print(f"\n  [bold magenta]{'  ' * depth}Analysis: {analysis_id}[/bold magenta]")
        _display_decisions(analysis_tree.get("decisions", {}), indent="  " * (depth + 1))
        _display_analysis_decisions(analysis_tree.get("analyses", {}), depth + 1)


@main.group()
def universe() -> None:
    """Universe management commands."""
    pass


@universe.command("generate")
@click.option("--name", "-n", default="baseline", help="Universe name/ID")
@click.option(
    "--analysis",
    "-a",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file (default: universes/<name>.yaml)",
)
@click.option("--description", "-d", help="Universe description")
def generate_universe(
    name: str,
    analysis: Path | None,
    output: Path | None,
    description: str | None,
) -> None:
    """Generate a universe from analysis defaults."""
    analysis_path = _require_analysis(analysis)
    data = load_yaml(analysis_path)

    # Check all decisions have defaults (across entire tree)
    missing_defaults: list[str] = []
    _check_missing_defaults(data, missing_defaults, "")
    if missing_defaults:
        console.print("[red]Error:[/red] Some decisions don't have defaults:")
        for d_id in missing_defaults:
            console.print(f"  • {d_id}")
        raise SystemExit(1)

    uni = create_universe_from_defaults(data, name, description)

    if output is None:
        output = analysis_path.parent / "universes" / f"{name}.yaml"

    output.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(uni, output)

    console.print(f"[green]✓[/green] Generated universe at [cyan]{output}[/cyan]")
    console.print("\nDecisions:")
    _print_universe_decisions(uni)


def _check_missing_defaults(node: dict[str, Any], missing: list[str], prefix: str = "") -> None:
    """Recursively check for decisions without defaults."""
    for d_id, d in _collect_node_decisions(node).items():
        if d.get("default") is None:
            missing.append(f"{prefix}{d_id}")
    for analysis_id, sub_node in (node.get("analyses") or {}).items():
        _check_missing_defaults(sub_node, missing, f"{prefix}{analysis_id}.")


def _print_universe_decisions(uni: dict[str, Any], indent: str = "  ") -> None:
    """Recursively print universe decisions."""
    for d_id, opt_id in (uni.get("decisions") or {}).items():
        console.print(f"{indent}{d_id}: {opt_id}")
    for analysis_id, sub in (uni.get("analyses") or {}).items():
        console.print(f"{indent}[magenta]{analysis_id}:[/magenta]")
        _print_universe_decisions(sub, indent + "  ")


@universe.command("check")
@click.argument("universe_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--analysis",
    "-a",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file",
)
def check_universe(universe_file: Path, analysis: Path | None) -> None:
    """Check a universe against its analysis constraints."""
    analysis_path = _require_analysis(analysis, universe_file.parent)
    errors = validate_universe_file(universe_file, analysis_path)

    if errors:
        console.print("[red]Universe validation errors:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        raise SystemExit(1)

    console.print("[green]✓[/green] Universe is valid")


@main.command()
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["mermaid", "ascii"]),
    default="ascii",
    help="Output format",
)
def viz(file: Path | None, fmt: str) -> None:
    """Visualize the decision space."""
    file = _require_analysis(file)
    data = load_yaml(file)

    if fmt == "mermaid":
        _viz_mermaid(data)
    else:
        _viz_ascii(data)


def _viz_ascii(data: dict[str, Any]) -> None:
    """Visualize decisions as ASCII tree."""
    tree = Tree(f"[bold]{data.get('name', 'Unknown')}[/bold]")
    _viz_ascii_node(tree, data)
    console.print(tree)


def _viz_ascii_node(parent_tree: Tree, node: dict[str, Any]) -> None:
    """Recursively add decisions to an ASCII tree."""
    decisions = _collect_node_decisions(node)
    for decision_id, decision in decisions.items():
        tags = decision.get("tags") or []
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        branch = parent_tree.add(f"[cyan]{decision_id}[/cyan]{tag_str}")

        options = decision.get("options", {})
        default = decision.get("default")
        for option_id, option in options.items():
            default_marker = " [default]" if option_id == default else ""
            constraints = []
            if option.get("incompatible_with"):
                constraints.append(f"\u2717 {', '.join(option['incompatible_with'])}")
            if option.get("requires"):
                constraints.append(f"\u2192 {', '.join(option['requires'])}")

            option_text = f"{option_id}: {option.get('label', '')}{default_marker}"
            if constraints:
                option_text += f" [dim]({'; '.join(constraints)})[/dim]"
            branch.add(option_text)

    for analysis_id, sub_node in (node.get("analyses") or {}).items():
        sub_tree = parent_tree.add(f"[bold magenta]{analysis_id}[/bold magenta]")
        _viz_ascii_node(sub_tree, sub_node)


def _viz_mermaid(data: dict[str, Any]) -> None:
    """Generate Mermaid diagram for decisions."""
    lines = ["graph TD"]

    _viz_mermaid_node(lines, data, "root")

    lines.append("")
    lines.append("    classDef default fill:#90EE90")

    console.print("\n".join(lines))


def _viz_mermaid_node(lines: list[str], node: dict[str, Any], node_prefix: str) -> None:
    """Recursively generate Mermaid subgraphs for an analysis node."""
    decisions = _collect_node_decisions(node)
    sub_analyses = node.get("analyses") or {}

    # If this node has decisions or sub-analyses, wrap in subgraph
    has_content = decisions or sub_analyses
    if has_content and node_prefix != "root":
        lines.append(f"    subgraph {node_prefix}[{node_prefix}]")

    for decision_id, decision in decisions.items():
        qualified = f"{node_prefix}__{decision_id}"
        lines.append(f"        {qualified}[{decision.get('label', decision_id)}]")

        options = decision.get("options", {})
        default = decision.get("default")
        for option_id, option in options.items():
            node_id = f"{qualified}_{option_id}"
            style = ":::default" if option_id == default else ""
            lines.append(f"        {node_id}(({option.get('label', option_id)})){style}")
            lines.append(f"        {qualified} --> {node_id}")

            if option.get("incompatible_with"):
                for ref in option["incompatible_with"]:
                    target = f"{node_prefix}__{ref.replace('.', '_')}"
                    lines.append(f"        {node_id} -.->|incompatible| {target}")

            if option.get("requires"):
                for ref in option["requires"]:
                    target = f"{node_prefix}__{ref.replace('.', '_')}"
                    lines.append(f"        {node_id} -->|requires| {target}")

    for analysis_id, sub_node in sub_analyses.items():
        _viz_mermaid_node(lines, sub_node, f"{node_prefix}__{analysis_id}")

    if has_content and node_prefix != "root":
        lines.append("    end")


@main.group()
def schema() -> None:
    """JSON Schema commands."""
    pass


@schema.command("export")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default="schemas",
    help="Output directory (default: schemas/)",
)
def schema_export(output: Path) -> None:
    """Export JSON schemas to files."""
    output.mkdir(parents=True, exist_ok=True)

    schemas = {
        "analysis.schema.json": get_analysis_schema(),
        "universe.schema.json": get_universe_schema(),
        "insights.schema.json": get_insights_schema(),
    }

    for name, schema_data in schemas.items():
        with open(output / name, "w") as f:
            json.dump(schema_data, f, indent=2)
            f.write("\n")

    console.print(f"[green]✓[/green] Exported schemas to [cyan]{output}/[/cyan]")
    console.print(f"  • {output}/analysis.schema.json")
    console.print(f"  • {output}/universe.schema.json")
    console.print(f"  • {output}/insights.schema.json")


@schema.command("show")
@click.argument("schema_type", type=click.Choice(["analysis", "universe", "insights"]))
def schema_show(schema_type: str) -> None:
    """Print a JSON schema to stdout."""
    schema_getters = {
        "analysis": get_analysis_schema,
        "universe": get_universe_schema,
        "insights": get_insights_schema,
    }
    schema_data = schema_getters[schema_type]()
    console.print(json.dumps(schema_data, indent=2))


# =============================================================================
# Paper commands
# =============================================================================


@main.group()
def paper() -> None:
    """Paper management commands for evidence verification."""
    pass


@paper.command("add")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option(
    "--pdf",
    type=click.Path(exists=True, path_type=Path),
    help="Use local PDF instead of downloading",
)
def paper_add(doi: str, version: int | None, pdf: Path | None) -> None:
    """Add a paper to the cache by DOI.

    DOI can be any valid DOI. For arXiv papers, use the format:
    10.48550/arXiv.1706.03762

    Examples:
        astra paper add 10.48550/arXiv.1706.03762 --version 7
        astra paper add 10.1038/s41586-023-06221-2
        astra paper add 10.1234/example --pdf ./local_paper.pdf
    """
    from astra.papers.cache import PaperCache
    from astra.papers.download import download_paper

    cache = PaperCache()

    # Check if already cached
    if cache.has(doi, version):
        paper = cache.get(doi, version)
        if paper:
            console.print(f"[yellow]Paper already cached:[/yellow] {doi}")
            console.print(f"  Path: {paper.pdf_path}")
            if paper.metadata.title:
                console.print(f"  Title: {paper.metadata.title}")
            return

    # Add from local file or download
    if pdf:
        console.print(f"Adding paper from local file: [cyan]{pdf}[/cyan]")
        paper = cache.add_from_file(doi, pdf, version=version)
        console.print("[green]✓[/green] Paper added to cache")
        console.print(f"  DOI: {doi}")
        if version:
            console.print(f"  Version: {version}")
        console.print(f"  Path: {paper.pdf_path}")
        console.print(f"  SHA-256: {paper.metadata.sha256[:16]}...")
    else:
        console.print(f"Downloading paper: [cyan]{doi}[/cyan]")
        if version:
            console.print(f"  Version: {version}")

        result = download_paper(doi, version)

        if not result.success:
            console.print(f"[red]Error:[/red] {result.error}")
            raise SystemExit(1)

        if result.content is None:
            console.print("[red]Error:[/red] No content received")
            raise SystemExit(1)

        paper = cache.add(
            doi=doi,
            pdf_content=result.content,
            version=version,
            title=result.title,
            authors=result.authors,
            source_url=result.url,
        )

        console.print("[green]✓[/green] Paper downloaded and cached")
        console.print(f"  DOI: {doi}")
        if version:
            console.print(f"  Version: {version}")
        if paper.metadata.title:
            console.print(f"  Title: {paper.metadata.title}")
        console.print(f"  Path: {paper.pdf_path}")
        console.print(f"  SHA-256: {paper.metadata.sha256[:16]}...")


@paper.command("list")
def paper_list() -> None:
    """List all cached papers."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    papers = cache.list_papers()

    if not papers:
        console.print("[dim]No papers cached[/dim]")
        return

    table = Table(show_header=True, expand=True)
    table.add_column("DOI", no_wrap=True)
    table.add_column("Ver", no_wrap=True)
    table.add_column("Title", ratio=2)
    table.add_column("Retrieved", no_wrap=True)

    for paper in papers:
        meta = paper.metadata
        version_str = str(meta.version) if meta.version else "-"
        title = meta.title or "[dim](unknown)[/dim]"
        retrieved = meta.retrieved_at[:10] if meta.retrieved_at else "-"
        table.add_row(meta.doi, version_str, title, retrieved)

    console.print(table)
    console.print(f"\n[dim]{len(papers)} paper(s) cached[/dim]")


@paper.command("show")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_show(doi: str, version: int | None) -> None:
    """Show details of a cached paper."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    paper = cache.get(doi, version)

    if not paper:
        console.print(f"[red]Error:[/red] Paper not found in cache: {doi}")
        if version:
            console.print(f"  (version {version})")
        console.print("\nUse [cyan]astra paper add[/cyan] to download the paper first.")
        raise SystemExit(1)

    meta = paper.metadata
    console.print(f"\n[bold]DOI:[/bold] {meta.doi}")
    if meta.version:
        console.print(f"[bold]Version:[/bold] {meta.version}")
    if meta.title:
        console.print(f"[bold]Title:[/bold] {meta.title}")
    if meta.authors:
        console.print(f"[bold]Authors:[/bold] {', '.join(meta.authors)}")
    console.print(f"[bold]SHA-256:[/bold] {meta.sha256}")
    console.print(f"[bold]Retrieved:[/bold] {meta.retrieved_at}")
    if meta.source_url:
        console.print(f"[bold]Source:[/bold] {meta.source_url}")
    console.print(f"[bold]Path:[/bold] {paper.pdf_path}")


@paper.command("path")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_path(doi: str, version: int | None) -> None:
    """Print the path to a cached paper's PDF.

    Useful for piping to other tools or agents that need to read the PDF.
    """
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    path = cache.get_path(doi, version)

    if not path:
        console.print(f"[red]Error:[/red] Paper not found: {doi}")
        raise SystemExit(1)

    # Print just the path (no formatting) for easy piping
    print(path)


@paper.command("remove")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_remove(doi: str, version: int | None) -> None:
    """Remove a paper from the cache."""
    from astra.papers.cache import PaperCache

    cache = PaperCache()

    if not cache.has(doi, version):
        console.print(f"[red]Error:[/red] Paper not found: {doi}")
        raise SystemExit(1)

    cache.remove(doi, version)
    console.print("[green]✓[/green] Paper removed from cache")


@paper.command("fetch-metadata")
@click.argument("doi", required=False)
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch metadata for all cached papers")
def paper_fetch_metadata(doi: str | None, version: int | None, fetch_all: bool) -> None:
    """Fetch metadata (title, authors) for cached papers.

    Uses DOI content negotiation to retrieve metadata from DOI.org.

    Examples:

        astra paper fetch-metadata 10.48550/arXiv.1706.03762

        astra paper fetch-metadata --all
    """
    from astra.papers.cache import PaperCache
    from astra.papers.download import fetch_doi_metadata

    cache = PaperCache()

    if fetch_all:
        papers = cache.list_papers()
        if not papers:
            console.print("[dim]No papers cached[/dim]")
            return

        updated = 0
        for paper in papers:
            meta = paper.metadata
            if meta.title and meta.authors:
                continue

            console.print(f"Fetching metadata for {meta.doi}...", end=" ")
            doi_meta = fetch_doi_metadata(meta.doi)

            if doi_meta.title or doi_meta.authors:
                cache.update_metadata(
                    meta.doi,
                    meta.version,
                    title=doi_meta.title,
                    authors=doi_meta.authors,
                )
                console.print(f"[green]✓[/green] {doi_meta.title or '(no title)'}")
                updated += 1
            else:
                console.print("[yellow]⚠[/yellow] No metadata found")

        console.print(f"\n[dim]Updated {updated} paper(s)[/dim]")
        return

    if not doi:
        console.print("[red]Error:[/red] Provide a DOI or use --all")
        raise SystemExit(1)

    if not cache.has(doi, version):
        console.print(f"[red]Error:[/red] Paper not found in cache: {doi}")
        raise SystemExit(1)

    console.print(f"Fetching metadata for {doi}...")
    doi_meta = fetch_doi_metadata(doi)

    if not doi_meta.title and not doi_meta.authors:
        console.print("[yellow]⚠[/yellow] No metadata found for this DOI")
        raise SystemExit(1)

    cache.update_metadata(doi, version, title=doi_meta.title, authors=doi_meta.authors)

    console.print("[green]✓[/green] Metadata updated:")
    if doi_meta.title:
        console.print(f"  Title: {doi_meta.title}")
    if doi_meta.authors:
        console.print(f"  Authors: {', '.join(doi_meta.authors)}")


@paper.command("verify-quotes")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_verify_quotes(doi: str, version: int | None) -> None:
    """Verify multiple quotes from a cached paper in a single operation.

    Reads quote list from stdin as JSON. Extracts PDF text once and
    verifies all quotes against it.

    Input format (stdin):
        {"quotes": [{"text": "...", "page": N, "prefix": "...", "suffix": "..."}, ...]}

    Output format (stdout, JSON):
        {"doi": "...", "results": [...], "summary": {...}}

    Exit codes:
      0 - All quotes verified
      1 - Some quotes not found
      2 - Error (paper not cached, invalid input, etc.)
    """
    from astra.papers.cache import PaperCache
    from astra.verification.core import VerificationStatus, verify_quote_in_pdf
    from astra.verification.pdf import extract_text_from_pdf

    # Read JSON input from stdin
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print(
                json.dumps(
                    {
                        "doi": doi,
                        "version": version,
                        "results": [],
                        "summary": {"total": 0, "verified": 0, "not_found": 0, "errors": 1},
                        "error": "No input provided on stdin",
                    }
                )
            )
            raise SystemExit(2)

        data = json.loads(input_data)
        quotes = data.get("quotes", [])
    except json.JSONDecodeError as e:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": 0, "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Invalid JSON input: {e}",
                }
            )
        )
        raise SystemExit(2)

    # Get paper from cache
    cache = PaperCache()
    cached_paper = cache.get(doi, version)

    if not cached_paper:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": len(quotes), "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Paper not in cache: {doi}",
                }
            )
        )
        raise SystemExit(2)

    # Extract text from PDF (ONCE)
    try:
        pdf = extract_text_from_pdf(cached_paper.pdf_path)
    except Exception as e:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": len(quotes), "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Failed to extract text from PDF: {e}",
                }
            )
        )
        raise SystemExit(2)

    # Verify each quote
    results = []
    verified_count = 0
    not_found_count = 0

    for idx, quote_data in enumerate(quotes):
        quote_text = quote_data.get("text", "")
        page_hint = quote_data.get("page")
        prefix = quote_data.get("prefix")
        suffix = quote_data.get("suffix")

        if not quote_text:
            results.append(
                {
                    "index": idx,
                    "text": "",
                    "status": "error",
                    "found_pages": [],
                    "message": "Empty quote text",
                }
            )
            continue

        status, found_pages, message = verify_quote_in_pdf(
            quote_text, pdf, page_hint, prefix, suffix
        )

        display_text = quote_text[:50] + "..." if len(quote_text) > 50 else quote_text

        results.append(
            {
                "index": idx,
                "text": display_text,
                "status": status.value,
                "found_pages": found_pages,
                "message": message,
            }
        )

        if status == VerificationStatus.VERIFIED:
            verified_count += 1
        else:
            not_found_count += 1

    # Output results
    output = {
        "doi": doi,
        "version": version,
        "results": results,
        "summary": {
            "total": len(quotes),
            "verified": verified_count,
            "not_found": not_found_count,
            "errors": 0,
        },
    }
    print(json.dumps(output))

    if not_found_count > 0:
        raise SystemExit(1)
    raise SystemExit(0)


@paper.command("verify-quote")
@click.argument("doi")
@click.option("--quote", "-q", required=True, help="Exact quote text to verify")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option("--page", "-p", type=int, help="Expected page number (1-indexed)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def paper_verify_quote(
    doi: str, quote: str, version: int | None, page: int | None, output_json: bool
) -> None:
    """Verify a quote exists in a cached paper.

    Searches for the exact quote in the paper's text. Uses fuzzy matching
    to handle minor OCR/extraction differences.

    Exit codes:
      0 - Quote verified (found in paper)
      1 - Quote not found
      2 - Error (paper not cached, etc.)
    """
    from astra.papers.cache import PaperCache
    from astra.verification.core import VerificationStatus, verify_quote_in_pdf
    from astra.verification.pdf import extract_text_from_pdf

    cache = PaperCache()
    cached_paper = cache.get(doi, version)

    if not cached_paper:
        if output_json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"Paper not in cache: {doi}",
                        "found_pages": [],
                        "expected_page": page,
                    }
                )
            )
        else:
            console.print(f"[red]Error:[/red] Paper not in cache: {doi}")
            console.print("Use [cyan]astra paper add[/cyan] first.")
        raise SystemExit(2)

    try:
        pdf = extract_text_from_pdf(cached_paper.pdf_path)
    except Exception as e:
        if output_json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"Failed to extract text from PDF: {e}",
                        "found_pages": [],
                        "expected_page": page,
                    }
                )
            )
        else:
            console.print(f"[red]Error:[/red] Failed to extract text from PDF: {e}")
        raise SystemExit(2)

    status, found_pages, message = verify_quote_in_pdf(quote, pdf, page)

    if output_json:
        print(
            json.dumps(
                {
                    "status": status.value,
                    "found_pages": found_pages,
                    "expected_page": page,
                    "message": message,
                }
            )
        )
    else:
        if status == VerificationStatus.VERIFIED:
            console.print(f"[green]✓ Verified[/green] {message}")
        else:
            console.print(f"[red]✗ Not found[/red] {message}")

    raise SystemExit(0 if status == VerificationStatus.VERIFIED else 1)


if __name__ == "__main__":
    main()
