"""Command-line interface for ASP."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from asp.helpers import (
    create_universe_from_defaults,
    get_chunk_decisions,
    get_decisions,
    get_inputs,
    get_outputs,
    load_yaml,
    save_yaml,
)
from asp.validation.schema import (
    get_analysis_schema,
    get_insights_schema,
    get_universe_schema,
    validate_analysis_schema,
    validate_universe_schema,
)
from asp.validation.semantic import validate_analysis_file, validate_universe_file
from asp.workflow.generator import generate_params_file, generate_params_string
from asp.workflow.parser import parse_cwl_inputs
from asp.workflow.validator import (
    get_decision_param_mapping,
    validate_decision_coverage,
)

console = Console()


def find_analysis_file(start_path: Path | None = None) -> Path | None:
    """Find the asp.yaml file in the current or parent directories."""
    if start_path is None:
        start_path = Path.cwd()

    # Resolve to absolute path to ensure parent traversal works correctly
    current = start_path.resolve()
    while current != current.parent:
        asp_file = current / "asp.yaml"
        if asp_file.exists():
            return asp_file
        current = current.parent

    return None


def _require_analysis(analysis: Path | None, start_path: Path | None = None) -> Path:
    """Find or validate analysis file, exit with error if not found."""
    if analysis is not None:
        return analysis
    found = find_analysis_file(start_path)
    if found is None:
        console.print("[red]Error:[/red] No asp.yaml found.")
        raise SystemExit(1)
    return found


@click.group()
@click.version_option()
def main() -> None:
    """ASP - Agentic Science Protocol CLI."""
    pass


@main.command()
@click.argument("directory", type=click.Path(path_type=Path), default=".")
@click.option("--no-git", is_flag=True, help="Don't initialize git repository")
@click.option("--no-venv", is_flag=True, help="Don't create Python virtual environment")
def init(directory: Path, no_git: bool, no_venv: bool) -> None:
    """Create a new ASP analysis project.

    Creates the project scaffolding for an ASP analysis with Claude Code
    plugin configuration and a Python virtual environment.

    DIRECTORY is the project folder to create (default: current directory).

    Examples:
        asp init my-analysis
        asp init my-analysis --no-git    # Without git initialization
        asp init my-analysis --no-venv   # Without virtual environment
    """
    # Create project directory
    if directory != Path("."):
        if directory.exists() and any(directory.iterdir()):
            if not click.confirm(
                f"[yellow]{directory}[/yellow] already exists and is not empty. Continue?"
            ):
                raise SystemExit(0)
        directory.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    subdirs = [
        "universes",
        "workflows",
        "steps",
        "results",
    ]
    for subdir in subdirs:
        (directory / subdir).mkdir(parents=True, exist_ok=True)

    # Create .gitignore
    gitignore = """# ASP Analysis
results/
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
.DS_Store
"""
    (directory / ".gitignore").write_text(gitignore)

    # Create boilerplate asp.yaml
    _create_boilerplate_asp_yaml(directory)

    # Create Claude Code settings with local skills
    _create_claude_settings(directory)

    # Create virtual environment
    venv_created = _create_venv(directory, no_venv)

    # Initialize git repository
    _init_git_repo(directory, no_git)

    # Print success message
    console.print(f"\n[green]✓[/green] Created ASP analysis project: [cyan]{directory}[/cyan]")
    includes = "asp.yaml, universes/, workflows/, steps/"
    if venv_created:
        includes += ", .venv/"
    console.print(f"[dim]  Includes: {includes}[/dim]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. [cyan]cd {directory}[/cyan]")
    console.print("  2. Run [cyan]claude[/cyan] to launch Claude Code")
    console.print("  3. Use [cyan]/asp:new[/cyan] to scope your research question")
    console.print()
    console.print("[dim]Available commands: /asp:new, /asp:build, /asp:insights[/dim]")


def _create_boilerplate_asp_yaml(directory: Path) -> None:
    """Create boilerplate asp.yaml with TODOs."""
    name = directory.name if directory != Path(".") else "My Analysis"

    asp_yaml = f'''# ASP Analysis Specification
# Documentation: https://github.com/EiffL/ASP

version: "1.0"

analysis:
  name: "{name}"
  problem: |
    TODO: What research question are you trying to answer?

  inputs:
    - id: primary_data
      type: data
      description: "TODO: Describe your primary data source"

  outputs:
    - id: main_result
      type: metric
      dtype: float
      description: "TODO: Describe your primary output metric"

    - id: conclusion
      type: report
      description: "Summary addressing the problem statement"

chunks:
  main:
    decisions:
      example_method:
        label: "Example Method Choice"
        type: method
        importance: 3
        rationale: "TODO: Explain why this decision matters"
        default: option_a
        options:
          option_a:
            label: "Option A"
            description: "TODO: Describe option A"
          option_b:
            label: "Option B"
            description: "TODO: Describe option B"
'''
    (directory / "asp.yaml").write_text(asp_yaml)

    # Create baseline universe
    baseline_universe = """# Baseline Universe
# Default configuration using standard practices

id: baseline
description: "Default configuration using standard practices"

chunks:
  main:
    example_method: option_a
"""
    (directory / "universes" / "baseline.yaml").write_text(baseline_universe)

    # Create README
    _create_readme(directory, name)


def _create_readme(directory: Path, name: str) -> None:
    """Create a README.md for the project."""
    readme = f"""# {name}

An ASP (Agentic Science Protocol) analysis project.

## Quick Start

```bash
# Validate the specification
asp validate asp.yaml

# Show analysis info
asp info

# Generate a universe from defaults
asp universe generate -n baseline
```

## Structure

- `asp.yaml` - Analysis specification (source of truth)
- `universes/` - Universe definitions (decision selections)
- `workflows/` - CWL workflow files
- `steps/` - Reusable workflow steps
- `results/` - Execution outputs (gitignored)

## Documentation

See [ASP documentation](https://github.com/LightconeResearch/ASP) for more information.
"""
    (directory / "README.md").write_text(readme)


def _get_plugin_source_dir() -> Path | None:
    """Find the ASP plugin source directory.

    Looks for the plugin files in:
    1. Bundled location (installed package): asp/claude/asp/
    2. Development location (repo): claude/asp/ relative to repo root
    """
    # Try bundled location first (installed package)
    import asp

    package_dir = Path(asp.__file__).parent
    bundled_plugin = package_dir / "claude" / "asp"
    if bundled_plugin.exists():
        return bundled_plugin

    # Try development location (running from repo)
    # Go up from src/asp/ to repo root, then into claude/asp/
    repo_root = package_dir.parent.parent
    dev_plugin = repo_root / "claude" / "asp"
    if dev_plugin.exists():
        return dev_plugin

    return None


def _create_claude_settings(directory: Path) -> None:
    """Create Claude Code settings with ASP plugin installed locally.

    Copies the full ASP plugin to .claude/plugins/asp/ so skills are
    invoked as /asp:new, /asp:build, etc. The plugin is auto-discovered
    by Claude Code when running in the project directory.
    """
    claude_dir = directory / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Find the plugin source directory
    plugin_source = _get_plugin_source_dir()
    if plugin_source is None:
        console.print(
            "[yellow]Warning:[/yellow] Could not find ASP plugin source files. "
            "Claude Code skills will not be available."
        )
        return

    # Copy entire plugin to .claude/plugins/asp/
    plugins_dir = claude_dir / "plugins"
    plugin_dst = plugins_dir / "asp"
    if plugin_dst.exists():
        shutil.rmtree(plugin_dst)
    shutil.copytree(plugin_source, plugin_dst)

    # Make scripts executable
    scripts_dst = plugin_dst / "scripts"
    if scripts_dst.exists():
        for script in scripts_dst.glob("*.sh"):
            script.chmod(script.stat().st_mode | 0o111)

    # Create marketplace.json in the plugin's .claude-plugin/ directory
    # This allows extraKnownMarketplaces to discover the plugin
    marketplace = {
        "name": "asp-local",
        "owner": {
            "name": "Lightcone Research",
        },
        "plugins": [
            {
                "name": "asp",
                "source": "./",
                "description": "Agentic Science Protocol - declarative scientific analyses",
            }
        ],
    }
    marketplace_file = plugin_dst / ".claude-plugin" / "marketplace.json"
    marketplace_file.write_text(json.dumps(marketplace, indent=2) + "\n")

    console.print("[green]✓[/green] Installed ASP plugin locally")

    # Create settings.json with local marketplace and permissions
    # extraKnownMarketplaces tells Claude Code where to find the plugin
    # enabledPlugins enables it automatically
    settings = {
        "permissions": {
            "allow": [
                "Bash(asp:*)",
                "Bash(python:*)",
                "Bash(cwltool:*)",
                "Edit",
                "WebSearch",
                "WebFetch",
            ],
        },
        "extraKnownMarketplaces": {
            "asp-local": {
                "source": {
                    "source": "directory",
                    "path": "./.claude/plugins/asp",
                },
            },
        },
        "enabledPlugins": {
            "asp@asp-local": True,
        },
    }

    settings_file = claude_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2) + "\n")


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
                ["git", "commit", "-m", "Initial ASP analysis structure"],
                cwd=directory,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            pass  # Commit failed, but repo is initialized
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Git not available


def _create_venv(directory: Path, no_venv: bool) -> bool:
    """Create a virtual environment with asp installed.

    Returns True if venv was created successfully.
    """
    if no_venv:
        return False

    venv_path = directory / ".venv"

    # Create the virtual environment
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning:[/yellow] Failed to create virtual environment: {e}")
        return False

    console.print("[green]✓[/green] Created virtual environment (.venv)")

    # Determine pip path
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip"
    else:
        pip_path = venv_path / "bin" / "pip"

    # Try to install asp from GitHub via SSH
    try:
        subprocess.run(
            [str(pip_path), "install", "git+ssh://git@github.com/LightconeResearch/ASP.git"],
            capture_output=True,
            check=True,
        )
        console.print("[green]✓[/green] Installed asp in virtual environment")
    except subprocess.CalledProcessError:
        console.print(
            "[yellow]Warning:[/yellow] Could not install asp (SSH auth may have failed). "
            "You can install manually with: .venv/bin/pip install asp"
        )

    return True


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--analysis",
    "-a",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file for universe validation",
)
def validate(file: Path, analysis: Path | None) -> None:
    """Validate an ASP specification file.

    FILE can be an analysis (asp.yaml) or universe file.
    For universe files, use --analysis to specify the analysis file.
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
    console.print("\n[green]Validation successful![/green]")


@main.command()
@click.argument("analysis", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("--insight", "-i", help="Verify specific insight by ID")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    help="Directory to cache downloaded PDFs",
)
def verify(analysis: Path | None, insight: str | None, cache_dir: Path | None) -> None:
    """Verify insight evidence exists in source documents.

    Downloads PDFs (arXiv only) and checks that quoted text exists.
    Results show whether evidence was verified, not found, or skipped.

    Examples:
        asp verify                           # Verify all insights
        asp verify asp.yaml                  # Explicit analysis file
        asp verify --insight scaling_paper   # Verify specific insight
    """
    try:
        from asp.verification import InsightVerification, VerificationStatus, verify_insight
    except ImportError:
        console.print("[red]Error:[/red] Verification requires optional dependencies.")
        console.print("Install with: [cyan]pip install asp[verify][/cyan]")
        raise SystemExit(1)

    analysis_path = _require_analysis(analysis)
    data = load_yaml(analysis_path)

    insights = data.get("insights", {})
    if not insights:
        console.print("[yellow]No insights found in analysis.[/yellow]")
        return

    # Filter to specific insight if requested
    if insight:
        if insight not in insights:
            console.print(f"[red]Error:[/red] Insight '{insight}' not found.")
            console.print(f"Available insights: {', '.join(insights.keys())}")
            raise SystemExit(1)
        insights = {insight: insights[insight]}

    console.print(f"Verifying [cyan]{len(insights)}[/cyan] insight(s)...\n")

    # Verify each insight
    results: list[InsightVerification] = []
    for insight_id, insight_data in insights.items():
        # Add id to insight data if not present (it's stored as the key)
        if "id" not in insight_data:
            insight_data["id"] = insight_id
        result = verify_insight(insight_data, cache_dir=cache_dir)
        results.append(result)

    # Display results table
    table = Table(show_header=True)
    table.add_column("Insight")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Details")

    status_colors = {
        VerificationStatus.VERIFIED: "green",
        VerificationStatus.NOT_FOUND: "red",
        VerificationStatus.WRONG_PAGE: "yellow",
        VerificationStatus.SKIPPED: "dim",
        VerificationStatus.ERROR: "red",
    }

    for result in results:
        color = status_colors.get(result.overall_status, "white")
        status_text = f"[{color}]{result.overall_status.value}[/{color}]"

        # Build details
        if result.evidence_results:
            verified = sum(
                1 for e in result.evidence_results if e.status == VerificationStatus.VERIFIED
            )
            total = len(result.evidence_results)
            details = f"{verified}/{total} evidence verified"
        else:
            details = ""

        table.add_row(result.insight_id, result.source_id, status_text, details)

    console.print(table)

    # Show detailed evidence results if there are issues
    failed_statuses = (
        VerificationStatus.NOT_FOUND,
        VerificationStatus.WRONG_PAGE,
        VerificationStatus.ERROR,
    )
    has_issues = any(r.overall_status in failed_statuses for r in results)

    if has_issues:
        console.print("\n[bold]Evidence Details:[/bold]")
        for result in results:
            if result.overall_status in failed_statuses:
                console.print(f"\n[cyan]{result.insight_id}[/cyan]:")
                for ev in result.evidence_results:
                    if ev.status != VerificationStatus.VERIFIED:
                        ev_color = status_colors.get(ev.status, "white")
                        console.print(f"  [{ev_color}]{ev.evidence_id}[/{ev_color}]: {ev.message}")

    # Summary
    verified_count = sum(1 for r in results if r.overall_status == VerificationStatus.VERIFIED)
    skipped_count = sum(1 for r in results if r.overall_status == VerificationStatus.SKIPPED)
    failed_count = len(results) - verified_count - skipped_count

    console.print()
    if failed_count == 0:
        console.print(f"[green]✓[/green] {verified_count} verified, {skipped_count} skipped")
    else:
        console.print(
            f"[red]✗[/red] {failed_count} failed, {verified_count} verified, "
            f"{skipped_count} skipped"
        )
        raise SystemExit(1)


@main.command()
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file (default: asp.yaml in current/parent dir)",
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

    analysis_section = data.get("analysis", {})

    # Header
    console.print(f"\n[bold]{analysis_section.get('name', 'Unknown')}[/bold]")
    console.print(f"Version: {data.get('version', 'Unknown')}")
    if analysis_section.get("description"):
        console.print(f"\n{analysis_section['description']}")

    # Problem statement
    console.print("\n[bold]Problem:[/bold]")
    console.print(analysis_section.get("problem", "").strip())

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
        table.add_column("Description")

        for out in output_list:
            table.add_row(out.get("id", ""), out.get("type", ""), out.get("description", ""))
        console.print(table)

    # Decisions (grouped by chunk)
    if decisions or show_all:
        console.print("\n[bold]Decisions:[/bold]")
        chunk_decisions = get_chunk_decisions(data)
        for chunk_id, chunk_decs in chunk_decisions.items():
            if len(chunk_decisions) > 1:
                console.print(f"\n  [bold magenta]Chunk: {chunk_id}[/bold magenta]")
            for decision_id, decision in chunk_decs.items():
                tree = Tree(f"[cyan]{decision_id}[/cyan]: {decision.get('label', '')}")
                tree.add(f"[dim]Type:[/dim] {decision.get('type', '')}")
                tree.add(f"[dim]Importance:[/dim] {decision.get('importance', 3)}/5")
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

    # Check all decisions have defaults (across all chunks)
    chunk_decs = get_chunk_decisions(data)
    missing_defaults: list[str] = []
    for chunk_id, decs in chunk_decs.items():
        for d_id, d in decs.items():
            if d.get("default") is None:
                missing_defaults.append(f"{chunk_id}.{d_id}")
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
    for chunk_id, chunk_selections in uni.get("chunks", {}).items():
        if len(uni.get("chunks", {})) > 1:
            console.print(f"  [magenta]{chunk_id}:[/magenta]")
        for d_id, opt_id in chunk_selections.items():
            console.print(f"  {d_id}: {opt_id}")


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
    analysis_name = data.get("analysis", {}).get("name", "Unknown")
    tree = Tree(f"[bold]{analysis_name}[/bold]")

    for chunk_id, decisions in get_chunk_decisions(data).items():
        chunk_branch = tree.add(f"[bold magenta]{chunk_id}[/bold magenta]")
        for decision_id, decision in decisions.items():
            importance = decision.get("importance", 3)
            importance_stars = "★" * importance + "☆" * (5 - importance)
            branch = chunk_branch.add(
                f"[cyan]{decision_id}[/cyan] ({decision.get('type', '')}) [{importance_stars}]"
            )

            options = decision.get("options", {})
            default = decision.get("default")
            for option_id, option in options.items():
                default_marker = " [default]" if option_id == default else ""
                constraints = []
                if option.get("incompatible_with"):
                    constraints.append(f"✗ {', '.join(option['incompatible_with'])}")
                if option.get("requires"):
                    constraints.append(f"→ {', '.join(option['requires'])}")

                option_text = f"{option_id}: {option.get('label', '')}{default_marker}"
                if constraints:
                    option_text += f" [dim]({'; '.join(constraints)})[/dim]"
                branch.add(option_text)

    console.print(tree)


def _viz_mermaid(data: dict[str, Any]) -> None:
    """Generate Mermaid diagram for decisions."""
    lines = ["graph TD"]

    for chunk_id, decisions in get_chunk_decisions(data).items():
        # Chunk subgraph
        lines.append(f"    subgraph {chunk_id}[{chunk_id}]")
        for decision_id, decision in decisions.items():
            # Use chunk-qualified node IDs to avoid collisions
            node_prefix = f"{chunk_id}__{decision_id}"
            # Decision node
            lines.append(f"        {node_prefix}[{decision.get('label', decision_id)}]")

            # Option nodes
            options = decision.get("options", {})
            default = decision.get("default")
            for option_id, option in options.items():
                node_id = f"{node_prefix}_{option_id}"
                style = ":::default" if option_id == default else ""
                lines.append(f"        {node_id}(({option.get('label', option_id)})){style}")
                lines.append(f"        {node_prefix} --> {node_id}")

                # Constraints
                if option.get("incompatible_with"):
                    for ref in option["incompatible_with"]:
                        # Constraints are chunk-scoped, qualify with current chunk
                        target = f"{chunk_id}__{ref.replace('.', '_')}"
                        lines.append(f"        {node_id} -.->|incompatible| {target}")

                if option.get("requires"):
                    for ref in option["requires"]:
                        target = f"{chunk_id}__{ref.replace('.', '_')}"
                        lines.append(f"        {node_id} -->|requires| {target}")
        lines.append("    end")

    lines.append("")
    lines.append("    classDef default fill:#90EE90")

    console.print("\n".join(lines))


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
    import json

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
    import json

    schema_getters = {
        "analysis": get_analysis_schema,
        "universe": get_universe_schema,
        "insights": get_insights_schema,
    }
    schema_data = schema_getters[schema_type]()
    console.print(json.dumps(schema_data, indent=2))


# =============================================================================
# Workflow commands
# =============================================================================


@main.command("params")
@click.argument("universe_file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write to file")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("--inputs/--no-inputs", default=True, help="Include ASP inputs as CWL File params")
def params(universe_file: Path, output: Path | None, analysis: Path | None, inputs: bool) -> None:
    """Generate CWL parameters from a universe.

    Outputs YAML to stdout by default. Use -o to write to a file.
    Includes ASP input files by default (use --no-inputs to exclude).
    """
    analysis_path = _require_analysis(analysis, universe_file.parent)
    spec = load_yaml(analysis_path)
    uni = load_yaml(universe_file)
    base_path = analysis_path.parent if inputs else None
    yaml_output = generate_params_string(spec, uni, include_inputs=inputs, base_path=base_path)

    if output is None:
        # Output to stdout (raw YAML, no Rich formatting)
        print(yaml_output, end="")
    else:
        generate_params_file(spec, uni, output, include_inputs=inputs, base_path=base_path)
        console.print(f"[green]✓[/green] Generated parameters at [cyan]{output}[/cyan]")


@main.group()
def workflow() -> None:
    """Workflow integration commands."""
    pass


@workflow.command("generate")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output path (default: workflows/main.cwl)",
)
def workflow_generate(analysis: Path | None, output: Path | None) -> None:
    """Generate CWL workflow skeleton from ASP specification.

    Creates a CWL Workflow with:
    - Inputs for data-type ASP inputs (as File type) and decisions
    - Outputs referencing step outputs via outputSource
    - A single step referencing steps/main.cwl

    The generated workflow is a starting point. Implement steps/main.cwl
    as a CommandLineTool with the actual analysis logic.
    """
    from asp.workflow.generator import generate_cwl_file

    analysis_path = _require_analysis(analysis)
    spec = load_yaml(analysis_path)

    # Default output path
    if output is None:
        output = analysis_path.parent / "workflows" / "main.cwl"

    # Check if file exists
    if output.exists():
        if not click.confirm(f"[yellow]{output}[/yellow] exists. Overwrite?"):
            console.print("Aborted.")
            return

    generate_cwl_file(spec, output)
    console.print(f"[green]✓[/green] Generated CWL workflow at [cyan]{output}[/cyan]")
    console.print("\nNext steps:")
    console.print("  1. Create [cyan]steps/main.cwl[/cyan] as a CommandLineTool")
    console.print("  2. Implement the analysis logic in your step")
    console.print(f"  3. Run: [cyan]asp workflow run universes/baseline.yaml --cwl {output}[/cyan]")


@workflow.command("validate")
@click.option("--cwl", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("--syntax-only", is_flag=True, help="Only validate CWL syntax, skip ASP mapping")
def workflow_validate(cwl: Path, analysis: Path | None, syntax_only: bool) -> None:
    """Validate CWL workflow against ASP decisions and CWL specification.

    Validates both CWL syntax (using cwltool) and ASP decision mapping.
    """
    from asp.workflow.validator import validate_cwl_syntax

    console.print(f"Validating [cyan]{cwl}[/cyan]...")

    # CWL syntax validation
    syntax_errors = validate_cwl_syntax(cwl)
    if syntax_errors:
        console.print("\n[red]CWL syntax errors:[/red]")
        for error in syntax_errors:
            console.print(f"  [red]ERROR[/red] {error}")
        raise SystemExit(1)
    console.print("[green]✓[/green] CWL syntax valid")

    if syntax_only:
        return

    # ASP mapping validation
    analysis_path = _require_analysis(analysis)
    spec = load_yaml(analysis_path)
    console.print(f"Checking mapping against [cyan]{analysis_path}[/cyan]...")

    errors = validate_decision_coverage(spec, cwl)
    if errors:
        console.print("\n[red]Mapping errors:[/red]")
        for error in errors:
            is_warning = error.code == "UNMAPPED_DECISION"
            level = "[yellow]WARN[/yellow]" if is_warning else "[red]ERROR[/red]"
            console.print(f"  {level} {error}")
        raise SystemExit(1)

    console.print("[green]✓[/green] All decisions map to CWL parameters")
    console.print("[green]✓[/green] All required CWL parameters are covered")


@workflow.command("show")
@click.option("--cwl", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def workflow_show(cwl: Path, analysis: Path | None) -> None:
    """Show CWL workflow inputs and their ASP mappings."""
    analysis_path = _require_analysis(analysis)
    spec = load_yaml(analysis_path)

    try:
        cwl_params = parse_cwl_inputs(cwl)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] CWL file not found: {cwl}")
        raise SystemExit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    decision_mapping = get_decision_param_mapping(spec, cwl)
    param_to_decision = {
        param: decision_id for decision_id, params in decision_mapping.items() for param in params
    }

    console.print(f"\n[bold]CWL Inputs: {cwl.name}[/bold]\n")

    table = Table(show_header=True)
    table.add_column("CWL Parameter")
    table.add_column("Type")
    table.add_column("Required")
    table.add_column("ASP Decision")
    table.add_column("Status")

    for p in cwl_params:
        decision = param_to_decision.get(p.name, "")
        if decision:
            status = "[green]mapped[/green]"
        elif not p.required:
            status = "[dim]optional[/dim]"
        else:
            status = "[yellow]unmapped[/yellow]"
        table.add_row(p.name, p.type, "Yes" if p.required else "No", decision, status)

    console.print(table)

    unmapped_required = [p for p in cwl_params if p.name not in param_to_decision and p.required]
    console.print(f"\n[dim]Mapped: {len(param_to_decision)}/{len(cwl_params)} parameters[/dim]")
    if unmapped_required:
        console.print(
            f"[yellow]Warning:[/yellow] {len(unmapped_required)} required parameters unmapped"
        )


@workflow.command("run")
@click.argument("universe_file", type=click.Path(exists=True, path_type=Path))
@click.option("--cwl", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--outdir", type=click.Path(path_type=Path), help="Output directory")
@click.option("--quiet", "-q", is_flag=True, help="Suppress cwltool progress output")
def workflow_run(
    universe_file: Path,
    cwl: Path,
    analysis: Path | None,
    outdir: Path | None,
    quiet: bool,
) -> None:
    """Run a CWL workflow with parameters from a universe.

    Generates CWL parameters (including input files) from the universe
    and executes the workflow using cwltool.

    Example:
        asp workflow run universes/baseline.yaml --cwl workflows/main.cwl
    """
    import tempfile

    from asp.workflow.mapping import resolve_inputs

    analysis_path = _require_analysis(analysis, universe_file.parent)
    spec = load_yaml(analysis_path)
    uni = load_yaml(universe_file)

    # Generate parameters including inputs
    base_path = analysis_path.parent
    params_yaml = generate_params_string(spec, uni, include_inputs=True, base_path=base_path)

    # Count resolved inputs for display
    resolved_inputs = resolve_inputs(spec, base_path)
    data_inputs = [i for i in get_inputs(spec) if i.get("type") == "data"]

    console.print(f"[dim]Universe:[/dim] {universe_file.name}")
    console.print(f"[dim]Workflow:[/dim] {cwl.name}")
    if data_inputs:
        console.print(f"[dim]Inputs:[/dim] {len(resolved_inputs)}/{len(data_inputs)} resolved")
    console.print()

    # Write params to temp file (cwltool needs a file path for complex inputs)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(params_yaml)
        params_file = Path(f.name)

    try:
        # Build cwltool command
        cmd = ["cwltool"]
        if quiet:
            cmd.append("--quiet")
        if outdir:
            outdir.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--outdir", str(outdir)])
        cmd.extend([str(cwl), str(params_file)])

        console.print(f"[dim]Running:[/dim] cwltool {cwl.name} <params>")
        console.print()

        # Run cwltool
        result = subprocess.run(cmd)

        if result.returncode != 0:
            raise SystemExit(result.returncode)

        console.print()
        console.print("[green]✓[/green] Workflow completed successfully")
        if outdir:
            console.print(f"[dim]Outputs in:[/dim] {outdir}")

    finally:
        # Clean up temp file
        params_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
