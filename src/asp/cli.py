"""Command-line interface for ASP."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from asp.models.analysis import Analysis
from asp.models.universe import Universe
from asp.schemas import export_schemas, get_analysis_schema, get_universe_schema
from asp.validation.schema import validate_analysis_schema, validate_universe_schema
from asp.validation.semantic import validate_analysis_file, validate_universe_file

console = Console()


def find_analysis_file(start_path: Path | None = None) -> Path | None:
    """Find the asp.yaml file in the current or parent directories."""
    if start_path is None:
        start_path = Path.cwd()

    current = start_path
    while current != current.parent:
        asp_file = current / "asp.yaml"
        if asp_file.exists():
            return asp_file
        current = current.parent

    return None


@click.group()
@click.version_option()
def main() -> None:
    """ASP - Agentic Science Protocol CLI."""
    pass


@main.command()
@click.argument("directory", type=click.Path(path_type=Path), default=".")
@click.option("--name", "-n", help="Analysis name (will prompt if not provided)")
@click.option("--problem", "-p", help="Problem statement (will prompt if not provided)")
@click.option("--no-git", is_flag=True, help="Don't initialize git repository")
def init(directory: Path, name: str | None, problem: str | None, no_git: bool) -> None:
    """Create a new ASP analysis project.

    Creates a complete project structure with asp.yaml, README, and standard
    directories for universes, workflows, scripts, and results.

    DIRECTORY is the project folder to create (default: current directory).
    """
    import subprocess

    # Prompt for required fields if not provided
    if name is None:
        default_name = directory.name if directory != Path(".") else "My Analysis"
        name = click.prompt("Analysis name", default=default_name)

    if problem is None:
        problem = click.prompt(
            "Problem statement",
            default="What research question are you trying to answer?",
        )

    # Create project directory
    if directory != Path("."):
        if directory.exists() and any(directory.iterdir()):
            if not click.confirm(
                f"[yellow]{directory}[/yellow] already exists and is not empty. Continue?"
            ):
                raise SystemExit(0)
        directory.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    subdirs = [
        "universes",
        "workflows/params",
        "steps/io",
        "steps/preprocessing",
        "steps/models",
        "steps/evaluation",
        "scripts",
        "results",
        ".asp",
    ]
    for subdir in subdirs:
        (directory / subdir).mkdir(parents=True, exist_ok=True)

    # Create asp.yaml
    asp_yaml = f'''# ASP Analysis Specification
# Documentation: https://github.com/EiffL/ASP

version: "1.0"

analysis:
  name: "{name}"
  problem: |
    {problem}

  inputs:
    - id: primary_data
      type: data
      description: "TODO: Describe your primary data source"

  outputs:
    - id: main_result
      type: metric
      dtype: float
      primary: true
      description: "TODO: Describe your primary output metric"

    - id: conclusion
      type: report
      description: "Summary addressing the problem statement"

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

decisions:
  example_method: option_a
"""
    (directory / "universes" / "baseline.yaml").write_text(baseline_universe)

    # Create README
    readme = f"""# {name}

## Problem Statement

{problem}

## Project Structure

```
{directory.name}/
├── asp.yaml              # Analysis specification
├── universes/            # Universe definitions (decision selections)
│   └── baseline.yaml     # Default universe
├── workflows/            # Generated workflows (CWL, Snakemake, etc.)
│   └── params/           # Workflow parameters per universe
├── steps/                # Reusable workflow steps
│   ├── io/               # Data loading steps
│   ├── preprocessing/    # Data preprocessing steps
│   ├── models/           # Model training steps
│   └── evaluation/       # Evaluation steps
├── scripts/              # Python/R implementation scripts
├── results/              # Execution outputs (gitignored)
└── .asp/                 # ASP metadata
```

## Quick Start

```bash
# Validate the analysis specification
asp validate asp.yaml

# Show analysis info
asp info

# Validate the baseline universe
asp universe check universes/baseline.yaml

# Visualize decision space
asp viz
```

## Universes

- **baseline**: {problem[:50]}...

## Decisions

| Decision | Type | Default | Description |
|----------|------|---------|-------------|
| example_method | method | option_a | TODO: Add description |

---
Generated with [ASP](https://github.com/EiffL/ASP)
"""
    (directory / "README.md").write_text(readme)

    # Create .gitignore
    gitignore = """# ASP Analysis - Git Ignore

# Execution results (large files, regenerated)
results/

# Python
__pycache__/
*.py[cod]
*$py.class
.Python
*.so
.eggs/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Jupyter
.ipynb_checkpoints/
"""
    (directory / ".gitignore").write_text(gitignore)

    # Create .asp/branches.yaml
    branches_yaml = """# Branch metadata for ASP analysis
# See: https://github.com/EiffL/ASP

branches: {}
"""
    (directory / ".asp" / "branches.yaml").write_text(branches_yaml)

    # Initialize git repository
    git_initialized = False
    if not no_git and not (directory / ".git").exists():
        try:
            subprocess.run(
                ["git", "init"],
                cwd=directory,
                capture_output=True,
                check=True,
            )
            git_initialized = True
            # Try to create initial commit (may fail if git user not configured)
            try:
                subprocess.run(
                    ["git", "add", "."],
                    cwd=directory,
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial ASP analysis structure"],
                    cwd=directory,
                    capture_output=True,
                    check=True,
                )
            except subprocess.CalledProcessError:
                pass  # Commit failed (e.g., no git user configured), but repo is initialized
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Git not available or init failed, continue without it

    # Print summary
    console.print(f"\n[green]✓[/green] Created ASP analysis project: [cyan]{directory}[/cyan]")
    console.print("\n[bold]Project structure:[/bold]")
    console.print(f"  {directory}/")
    console.print("  ├── asp.yaml              [dim]# Analysis specification[/dim]")
    console.print("  ├── README.md             [dim]# Project documentation[/dim]")
    console.print("  ├── universes/            [dim]# Decision selections[/dim]")
    console.print("  │   └── baseline.yaml")
    console.print("  ├── workflows/            [dim]# Generated workflows[/dim]")
    console.print("  ├── steps/                [dim]# Reusable workflow steps[/dim]")
    console.print("  ├── scripts/              [dim]# Implementation scripts[/dim]")
    console.print("  ├── results/              [dim]# Outputs (gitignored)[/dim]")
    console.print("  └── .asp/                 [dim]# Metadata[/dim]")

    if git_initialized:
        console.print("\n[green]✓[/green] Initialized git repository")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. [cyan]cd {directory}[/cyan]")
    console.print("  2. Edit [cyan]asp.yaml[/cyan] to define your inputs, outputs, and decisions")
    console.print("  3. Run [cyan]asp validate asp.yaml[/cyan] to check your spec")
    console.print("  4. Run [cyan]asp info[/cyan] to see a summary")


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
    if file is None:
        file = find_analysis_file()
        if file is None:
            console.print("[red]Error:[/red] No asp.yaml found in current or parent directories.")
            raise SystemExit(1)

    analysis = Analysis.from_yaml(file)

    # Header
    console.print(f"\n[bold]{analysis.analysis.name}[/bold]")
    console.print(f"Version: {analysis.version}")
    if analysis.analysis.description:
        console.print(f"\n{analysis.analysis.description}")

    # Problem statement
    console.print("\n[bold]Problem:[/bold]")
    console.print(analysis.analysis.problem.strip())

    # Summary stats
    console.print(
        f"\n[dim]Inputs: {len(analysis.analysis.inputs)} | "
        f"Outputs: {len(analysis.analysis.outputs)} | "
        f"Decisions: {len(analysis.decisions)}[/dim]"
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

        for inp in analysis.analysis.inputs:
            table.add_row(inp.id, inp.type, inp.description or "")
        console.print(table)

    # Outputs
    if outputs or show_all:
        console.print("\n[bold]Outputs:[/bold]")
        table = Table(show_header=True)
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Primary")
        table.add_column("Description")

        for out in analysis.analysis.outputs:
            primary = "✓" if out.primary else ""
            table.add_row(out.id, out.type, primary, out.description or "")
        console.print(table)

    # Decisions
    if decisions or show_all:
        console.print("\n[bold]Decisions:[/bold]")
        for decision_id, decision in analysis.decisions.items():
            tree = Tree(f"[cyan]{decision_id}[/cyan]: {decision.label}")
            tree.add(f"[dim]Type:[/dim] {decision.type}")
            tree.add(f"[dim]Importance:[/dim] {decision.importance}/5")
            if decision.rationale:
                tree.add(f"[dim]Rationale:[/dim] {decision.rationale}")

            options_branch = tree.add("[dim]Options:[/dim]")
            for option_id, option in decision.options.items():
                default_marker = (
                    " [yellow](default)[/yellow]" if option_id == decision.default else ""
                )
                option_text = f"{option_id}: {option.label}{default_marker}"
                if option.description:
                    option_text += f" - [dim]{option.description}[/dim]"
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
    if analysis is None:
        analysis = find_analysis_file()
        if analysis is None:
            console.print("[red]Error:[/red] No asp.yaml found.")
            raise SystemExit(1)

    spec = Analysis.from_yaml(analysis)

    # Check all decisions have defaults
    missing_defaults = [d_id for d_id, d in spec.decisions.items() if d.default is None]
    if missing_defaults:
        console.print("[red]Error:[/red] Some decisions don't have defaults:")
        for d_id in missing_defaults:
            console.print(f"  • {d_id}")
        raise SystemExit(1)

    universe = Universe.from_defaults(spec, name, description)

    if output is None:
        output = analysis.parent / "universes" / f"{name}.yaml"

    output.parent.mkdir(parents=True, exist_ok=True)
    universe.to_yaml(output)

    console.print(f"[green]✓[/green] Generated universe at [cyan]{output}[/cyan]")
    console.print("\nDecisions:")
    for d_id, opt_id in universe.decisions.items():
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
    if analysis is None:
        analysis = find_analysis_file(universe_file.parent)
        if analysis is None:
            console.print("[red]Error:[/red] No asp.yaml found.")
            raise SystemExit(1)

    errors = validate_universe_file(universe_file, analysis)

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
    if file is None:
        file = find_analysis_file()
        if file is None:
            console.print("[red]Error:[/red] No asp.yaml found.")
            raise SystemExit(1)

    analysis = Analysis.from_yaml(file)

    if fmt == "mermaid":
        _viz_mermaid(analysis)
    else:
        _viz_ascii(analysis)


def _viz_ascii(analysis: Analysis) -> None:
    """Visualize decisions as ASCII tree."""
    tree = Tree(f"[bold]{analysis.analysis.name}[/bold]")

    for decision_id, decision in analysis.decisions.items():
        importance_stars = "★" * decision.importance + "☆" * (5 - decision.importance)
        branch = tree.add(f"[cyan]{decision_id}[/cyan] ({decision.type}) [{importance_stars}]")

        for option_id, option in decision.options.items():
            default = " [default]" if option_id == decision.default else ""
            constraints = []
            if option.incompatible_with:
                constraints.append(f"✗ {', '.join(option.incompatible_with)}")
            if option.requires:
                constraints.append(f"→ {', '.join(option.requires)}")

            option_text = f"{option_id}: {option.label}{default}"
            if constraints:
                option_text += f" [dim]({'; '.join(constraints)})[/dim]"
            branch.add(option_text)

    console.print(tree)


def _viz_mermaid(analysis: Analysis) -> None:
    """Generate Mermaid diagram for decisions."""
    lines = ["graph TD"]

    for decision_id, decision in analysis.decisions.items():
        # Decision node
        lines.append(f"    {decision_id}[{decision.label}]")

        # Option nodes
        for option_id, option in decision.options.items():
            node_id = f"{decision_id}_{option_id}"
            style = ":::default" if option_id == decision.default else ""
            lines.append(f"    {node_id}(({option.label})){style}")
            lines.append(f"    {decision_id} --> {node_id}")

            # Constraints
            if option.incompatible_with:
                for ref in option.incompatible_with:
                    target = ref.replace(".", "_")
                    lines.append(f"    {node_id} -.->|incompatible| {target}")

            if option.requires:
                for ref in option.requires:
                    target = ref.replace(".", "_")
                    lines.append(f"    {node_id} -->|requires| {target}")

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

    export_schemas(output)

    console.print(f"[green]✓[/green] Exported schemas to [cyan]{output}/[/cyan]")
    console.print(f"  • {output}/analysis.schema.json")
    console.print(f"  • {output}/universe.schema.json")
    console.print(f"  • {output}/insights.schema.json")


@schema.command("show")
@click.argument("schema_type", type=click.Choice(["analysis", "universe", "insights"]))
def schema_show(schema_type: str) -> None:
    """Print a JSON schema to stdout."""
    import json

    from asp.schemas import get_insights_schema

    if schema_type == "analysis":
        schema_data = get_analysis_schema()
    elif schema_type == "universe":
        schema_data = get_universe_schema()
    else:
        schema_data = get_insights_schema()

    console.print(json.dumps(schema_data, indent=2))


if __name__ == "__main__":
    main()
