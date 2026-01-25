"""Command-line interface for ASP."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from asp.models.analysis import Analysis
from asp.models.universe import Universe
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
def init(directory: Path, no_git: bool) -> None:
    """Create a new ASP analysis project.

    Creates the project scaffolding for an ASP analysis with Claude Code
    plugin configuration.

    DIRECTORY is the project folder to create (default: current directory).

    Examples:
        asp init my-analysis
        asp init my-analysis --no-git   # Without git initialization
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
        "steps/io",
        "steps/preprocessing",
        "steps/models",
        "steps/evaluation",
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

    # Create Claude Code settings to auto-install ASP plugin
    _create_claude_settings(directory)

    # Initialize git repository
    _init_git_repo(directory, no_git)

    # Print success message
    console.print(f"\n[green]✓[/green] Created ASP analysis project: [cyan]{directory}[/cyan]")
    console.print("[dim]  Includes: asp.yaml, universes/, workflows/, steps/, .claude/[/dim]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. [cyan]cd {directory}[/cyan]")
    console.print("  2. Run [cyan]claude[/cyan] to launch Claude Code (ASP plugin auto-installs)")
    console.print("  3. Edit [cyan]asp.yaml[/cyan] to define inputs, outputs, and decisions")
    console.print("  4. Run [cyan]asp validate asp.yaml[/cyan] to check your spec")


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


def _create_claude_settings(directory: Path) -> None:
    """Create Claude Code settings to auto-install ASP plugin."""
    claude_dir = directory / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "extraKnownMarketplaces": {
            "asp-plugins": {
                "source": {
                    "source": "github",
                    "repo": "LightconeResearch/ASP",
                }
            }
        },
        "enabledPlugins": {"asp-analysis@asp-plugins": True},
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
    file = _require_analysis(file)
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
    analysis = _require_analysis(analysis)
    spec = Analysis.from_yaml(analysis)

    # Check all decisions have defaults
    missing_defaults = [d_id for d_id, d in spec.decisions.items() if d.default is None]
    if missing_defaults:
        console.print("[red]Error:[/red] Some decisions don't have defaults:")
        for d_id in missing_defaults:
            console.print(f"  • {d_id}")
        raise SystemExit(1)

    uni = Universe.from_defaults(spec, name, description)

    if output is None:
        output = analysis.parent / "universes" / f"{name}.yaml"

    output.parent.mkdir(parents=True, exist_ok=True)
    uni.to_yaml(output)

    console.print(f"[green]✓[/green] Generated universe at [cyan]{output}[/cyan]")
    console.print("\nDecisions:")
    for d_id, opt_id in uni.decisions.items():
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
    analysis = _require_analysis(analysis, universe_file.parent)
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
    file = _require_analysis(file)
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
    spec = Analysis.from_yaml(analysis_path)
    uni = Universe.from_yaml(universe_file)
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

    Creates a CWL CommandLineTool with inputs for each ASP input and decision,
    and outputs for each ASP output. The generated workflow is a starting point
    that should be customized with the actual implementation.
    """
    from asp.workflow.generator import generate_cwl_file

    analysis_path = _require_analysis(analysis)
    spec = Analysis.from_yaml(analysis_path)

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
    console.print("  1. Edit [cyan]scripts/main.py[/cyan] to implement your analysis")
    console.print("  2. Update baseCommand and output globs in the CWL file")
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
    spec = Analysis.from_yaml(analysis_path)
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
    spec = Analysis.from_yaml(analysis_path)

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
    spec = Analysis.from_yaml(analysis_path)
    uni = Universe.from_yaml(universe_file)

    # Generate parameters including inputs
    base_path = analysis_path.parent
    params_yaml = generate_params_string(spec, uni, include_inputs=True, base_path=base_path)

    # Count resolved inputs for display
    resolved_inputs = resolve_inputs(spec, base_path)
    data_inputs = [i for i in spec.analysis.inputs if i.type == "data"]

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
