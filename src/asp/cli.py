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
    directories for universes, workflows, steps, and results.

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
        "workflows",
        "steps/io",
        "steps/preprocessing",
        "steps/models",
        "steps/evaluation",
        "results",
        ".asp",
        ".claude/skills/asp-analysis",
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
├── universes/            # Decision selections (source of truth for params)
│   └── baseline.yaml     # Default universe
├── workflows/            # CWL workflow definitions
├── steps/                # CWL workflow steps (all implementation here)
│   ├── io/               # Data loading steps
│   ├── preprocessing/    # Data preprocessing steps
│   ├── models/           # Model training steps
│   └── evaluation/       # Evaluation steps
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

    # Copy Claude skill from package templates
    import importlib.resources

    skill_template = importlib.resources.files("asp.templates").joinpath("SKILL.md")
    skill_content = skill_template.read_text()
    (directory / ".claude" / "skills" / "asp-analysis" / "SKILL.md").write_text(skill_content)

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
    console.print("  ├── workflows/            [dim]# CWL workflows[/dim]")
    console.print("  ├── steps/                [dim]# CWL workflow steps[/dim]")
    console.print("  ├── results/              [dim]# Outputs (gitignored)[/dim]")
    console.print("  ├── .asp/                 [dim]# Metadata[/dim]")
    console.print("  └── .claude/              [dim]# Claude Code skill[/dim]")

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


# =============================================================================
# Workflow commands
# =============================================================================


def _require_analysis(analysis: Path | None, start_path: Path | None = None) -> Path:
    """Find or validate analysis file, exit with error if not found."""
    if analysis is not None:
        return analysis
    found = find_analysis_file(start_path)
    if found is None:
        console.print("[red]Error:[/red] No asp.yaml found.")
        raise SystemExit(1)
    return found


@main.command("params")
@click.argument("universe_file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write to file")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def params(universe_file: Path, output: Path | None, analysis: Path | None) -> None:
    """Generate CWL parameters from a universe.

    Outputs YAML to stdout by default. Use -o to write to a file.
    """
    analysis = _require_analysis(analysis, universe_file.parent)
    spec = Analysis.from_yaml(analysis)
    universe = Universe.from_yaml(universe_file)
    yaml_output = generate_params_string(spec, universe)

    if output is None:
        # Output to stdout (raw YAML, no Rich formatting)
        print(yaml_output, end="")
    else:
        generate_params_file(spec, universe, output)
        console.print(f"[green]✓[/green] Generated parameters at [cyan]{output}[/cyan]")


@main.group()
def workflow() -> None:
    """Workflow integration commands."""
    pass


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
    analysis = _require_analysis(analysis)
    spec = Analysis.from_yaml(analysis)
    console.print(f"Checking mapping against [cyan]{analysis}[/cyan]...")

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
    analysis = _require_analysis(analysis)
    spec = Analysis.from_yaml(analysis)

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
        param: decision_id
        for decision_id, params in decision_mapping.items()
        for param in params
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

    Generates CWL parameters from the universe and executes the workflow
    using cwltool.

    Example:
        asp workflow run universes/baseline.yaml --cwl workflows/main.cwl
    """
    import subprocess
    import tempfile

    analysis = _require_analysis(analysis, universe_file.parent)
    spec = Analysis.from_yaml(analysis)
    universe = Universe.from_yaml(universe_file)

    # Generate parameters
    params_yaml = generate_params_string(spec, universe)

    console.print(f"[dim]Universe:[/dim] {universe_file.name}")
    console.print(f"[dim]Workflow:[/dim] {cwl.name}")
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
