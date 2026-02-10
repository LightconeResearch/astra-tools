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
@click.option(
    "--target",
    type=str,
    default=None,
    help="Remote cluster target (e.g., perlmutter). Creates asp-remote.yaml.",
)
def init(directory: Path, no_git: bool, no_venv: bool, target: str | None) -> None:
    """Create a new ASP analysis project.

    Creates the project scaffolding for an ASP analysis with Claude Code
    plugin configuration and a Python virtual environment.

    DIRECTORY is the project folder to create (default: current directory).

    Examples:
        asp init my-analysis
        asp init my-analysis --no-git    # Without git initialization
        asp init my-analysis --no-venv   # Without virtual environment
        asp init my-analysis --target perlmutter  # With remote cluster support
    """
    # Check if this is already an ASP project
    if (directory / "asp.yaml").exists():
        console.print(
            f"[red]Error:[/red] [cyan]{directory}[/cyan] is already an ASP project "
            f"(asp.yaml exists)."
        )
        console.print("Use [cyan]asp validate[/cyan] to check it, or delete asp.yaml to re-init.")
        raise SystemExit(1)

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
.asp/
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
.DS_Store
"""
    (directory / ".gitignore").write_text(gitignore)

    # Create boilerplate asp.yaml
    _create_boilerplate_asp_yaml(directory)

    # Create CLAUDE.md with ASP conventions
    _create_claude_md(directory, target=target)

    # Create Claude Code settings with local skills
    _create_claude_settings(directory, target=target)

    # Create remote config if target specified
    if target:
        _create_remote_config(directory, target)

    # Create virtual environment
    venv_created = _create_venv(directory, no_venv)

    # Initialize git repository
    _init_git_repo(directory, no_git)

    # Print success message
    console.print(f"[green]✓[/green] Created ASP analysis project: [cyan]{directory}[/cyan]")

    if target:
        console.print(f"\n[bold]Remote target:[/bold] {target}")
        console.print("\nNext steps:")
        console.print(f"  1. [bold]cd {directory}[/bold]")
        console.print("  2. Edit [cyan]asp-remote.yaml[/cyan] with your cluster details")
        console.print("  3. Run [cyan]sshproxy.sh[/cyan] to get SSH certificate")
        console.print("  4. Run [cyan]asp remote setup[/cyan] to test SSH connectivity")
        console.print("  5. Run [cyan]claude[/cyan] and use [cyan]/asp:new[/cyan]")
    else:
        console.print(f"\n[bold]cd {directory}[/bold], then either:")
        console.print("  • [cyan]asp canvas[/cyan] to open the visual canvas")
        console.print("  • [cyan]claude[/cyan] to work from the command line")
        console.print("\nThen run [cyan]/asp:new[/cyan] to scope your research question.")


@main.command()
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--name", "-n", help="Analysis name (default: directory name)")
def migrate(directory: Path, name: str | None) -> None:
    """Migrate an existing codebase to ASP.

    Creates ASP scaffolding for an existing project without overwriting
    existing files. Generates a MIGRATION.md checklist and placeholder
    asp.yaml for Claude to fill in.

    Unlike 'init', this command:
    - Won't create a new git repo or venv (assumes they exist)
    - Creates MIGRATION.md with a checklist for the migration
    - Creates a minimal asp.yaml placeholder (not the full boilerplate)

    Run '/asp-migrate' in Claude Code to have Claude analyze the codebase
    and draft the full specification.

    Examples:
        asp migrate .                    # Migrate current directory
        asp migrate ./my-project         # Migrate specific directory
        asp migrate . --name "My Study"  # Specify analysis name
    """
    directory = directory.resolve()

    if name is None:
        name = directory.name

    # Check if already an ASP project
    if (directory / "asp.yaml").exists():
        console.print(f"[yellow]Warning:[/yellow] {directory / 'asp.yaml'} already exists")
        if not click.confirm("Overwrite asp.yaml?"):
            console.print("Aborted. Run [cyan]/asp-migrate[/cyan] to refine existing spec.")
            raise SystemExit(0)

    # Create ASP directories (don't fail if they exist)
    subdirs = ["universes", "workflows", "steps", "results"]
    for subdir in subdirs:
        (directory / subdir).mkdir(parents=True, exist_ok=True)

    # Create minimal asp.yaml placeholder
    _create_migrate_asp_yaml(directory, name)

    # Create MIGRATION.md checklist
    _create_migration_checklist(directory, name)

    # Create Claude Code settings
    _create_claude_settings(directory)

    # Update .gitignore if it exists, or create minimal one
    _update_gitignore_for_asp(directory)

    console.print(f"[green]✓[/green] Prepared [cyan]{directory}[/cyan] for ASP migration")
    console.print("\nCreated:")
    console.print("  • [cyan]asp.yaml[/cyan] - placeholder specification")
    console.print("  • [cyan]MIGRATION.md[/cyan] - migration checklist")
    console.print("  • [cyan].claude/[/cyan] - Claude Code configuration")
    console.print("\nNext steps:")
    console.print(f"  1. [bold]cd {directory}[/bold]")
    console.print("  2. [bold]claude[/bold]")
    console.print("  3. Run [cyan]/asp-migrate[/cyan] to analyze codebase and draft spec")


def _create_migrate_asp_yaml(directory: Path, name: str) -> None:
    """Create minimal asp.yaml placeholder for migration."""
    asp_yaml = f"""# ASP Analysis Specification
# Generated by: asp migrate
# Complete this with: /asp-migrate

version: "1.0"

analysis:
  name: "{name}"
  problem: |
    TODO: Describe the research question this analysis answers.
    (Claude will draft this based on codebase analysis)

  inputs: []    # TODO: Define data inputs
  outputs: []   # TODO: Define outputs/artefacts

chunks:
  main:
    decisions: {{}}  # TODO: Extract decisions from codebase
"""
    (directory / "asp.yaml").write_text(asp_yaml)


def _create_migration_checklist(directory: Path, name: str) -> None:
    """Create MIGRATION.md with migration checklist."""
    checklist = f"""# ASP Migration Checklist

Analysis: **{name}**
Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}

## Overview

This project is being migrated to ASP (Agentic Science Protocol). Use `/asp-migrate` in Claude Code to have Claude analyze the codebase and draft the specification.

## Migration Status

### 1. Problem Statement
- [ ] Research question identified
- [ ] Success criteria defined
- [ ] Scope boundaries clear

### 2. Inputs
- [ ] Data sources identified
- [ ] Input files/URLs documented
- [ ] Data types specified

### 3. Outputs
- [ ] Primary outputs defined
- [ ] Artefacts (figures, tables, reports) listed
- [ ] Output types specified

### 4. Decisions
- [ ] Methodological choices extracted
- [ ] Parameter choices identified
- [ ] Defaults assigned
- [ ] Rationale documented

### 5. Chunks (Pipeline Stages)
- [ ] Single `main` chunk OR multiple stages identified
- [ ] Chunk boundaries clear
- [ ] Inter-chunk dependencies documented

### 6. Validation
- [ ] `asp validate asp.yaml` passes
- [ ] Baseline universe generated
- [ ] Universe validates against spec

## Decision Candidates

*Claude will populate this section with decisions found in the codebase.*

| Location | Decision Type | Current Choice | Notes |
|----------|--------------|----------------|-------|
| | | | |

## Files to Review

*Key files that likely contain decision points:*

- [ ] Configuration files (config.*, *.yaml, *.json)
- [ ] Main entry points
- [ ] Model/algorithm definitions
- [ ] Preprocessing pipelines

## Notes

*Add any notes about the migration here.*

---

See [decisions-reference.md](https://github.com/LightconeResearch/ASP/blob/main/docs/decisions-reference.md) for guidance on what counts as a decision.
"""
    (directory / "MIGRATION.md").write_text(checklist)


def _update_gitignore_for_asp(directory: Path) -> None:
    """Update or create .gitignore with ASP entries."""
    gitignore_path = directory / ".gitignore"
    asp_entries = """
# ASP
results/
.asp-cache/
"""
    if gitignore_path.exists():
        existing = gitignore_path.read_text()
        if "# ASP" not in existing:
            with open(gitignore_path, "a") as f:
                f.write(asp_entries)
    else:
        gitignore = """# ASP Analysis
results/
.asp-cache/
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
.DS_Store
"""
        gitignore_path.write_text(gitignore)


def _create_boilerplate_asp_yaml(directory: Path) -> None:
    """Create boilerplate asp.yaml with TODOs."""
    name = directory.name if directory != Path(".") else "My Analysis"

    asp_yaml = f"""# ASP Analysis Specification
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
"""
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
# Open in Claude Code
claude

# Scope the analysis
/asp-new

# Then start building (Claude reads CLAUDE.md for conventions)
```

## Structure

- `asp.yaml` — Analysis specification (source of truth)
- `CLAUDE.md` — Build conventions and project context for Claude Code
- `universes/` — Decision selections (one YAML per universe)
- `workflows/` — CWL workflow definitions
- `steps/` — Workflow step implementations
- `results/` — Execution outputs (gitignored)

## Documentation

See [ASP documentation](https://github.com/LightconeResearch/ASP) for more information.
"""
    (directory / "README.md").write_text(readme)


def _create_claude_md(directory: Path, target: str | None = None) -> None:
    """Create CLAUDE.md from the template in the plugin source.

    Copies the template and substitutes {{name}} with the project name.
    The /asp-new skill fills in project-specific sections later.
    When a remote target is specified, appends a Remote Execution section.
    """
    name = directory.name if directory != Path(".") else "My Analysis"

    # Find the template
    plugin_source = _get_plugin_source_dir()
    template_path = plugin_source / "templates" / "CLAUDE.md" if plugin_source else None

    if template_path and template_path.exists():
        content = template_path.read_text()
        content = content.replace("{{name}}", name)
    else:
        # Fallback: minimal CLAUDE.md if template not found
        content = (
            f"# CLAUDE.md\n\n## Project: {name}\n\n"
            "This is an ASP analysis project. Read `asp.yaml` for the specification.\n\n"
            "Read `.claude/skills/asp/SKILL.md` for how ASP works.\n"
        )

    # Append remote execution section if target is specified
    if target:
        content += _generate_remote_claude_section(target)

    (directory / "CLAUDE.md").write_text(content)


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


def _create_claude_settings(directory: Path, target: str | None = None) -> None:
    """Create Claude Code settings with ASP skills and agents."""
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

    # Copy scripts
    scripts_src = plugin_source / "scripts"
    scripts_dst = claude_dir / "scripts"
    if scripts_src.exists():
        if scripts_dst.exists():
            shutil.rmtree(scripts_dst)
        shutil.copytree(scripts_src, scripts_dst)
        # Make scripts executable
        for script in scripts_dst.glob("*.sh"):
            script.chmod(script.stat().st_mode | 0o111)

    # Copy skills
    skills_src = plugin_source / "skills"
    skills_dst = claude_dir / "skills"
    if skills_src.exists():
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(skills_src, skills_dst)

    # Copy agents (for sub-agent spawning)
    agents_src = plugin_source / "agents"
    agents_dst = claude_dir / "agents"
    if agents_src.exists():
        if agents_dst.exists():
            shutil.rmtree(agents_dst)
        shutil.copytree(agents_src, agents_dst)

    # Create settings.json with hooks configured directly (no marketplace)
    settings: dict[str, Any] = {
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
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": ".claude/scripts/activate-venv.sh",
                            "timeout": 5,
                        },
                        {
                            "type": "command",
                            "command": ".claude/scripts/session-start.sh",
                            "timeout": 10,
                        },
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": ".claude/scripts/validate-on-save.sh",
                            "timeout": 15,
                        },
                    ],
                },
            ],
        },
    }

    settings_file = claude_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2) + "\n")


def _create_remote_config(directory: Path, target: str) -> None:
    """Create asp-remote.yaml with cluster configuration template."""
    # Cluster-specific defaults
    cluster_defaults: dict[str, dict[str, Any]] = {
        "perlmutter": {
            "backend": "ssh",
            "ssh_host": "perlmutter.nersc.gov",
            "ssh_user": "FIXME",
            "account": "FIXME",
            "workdir": "FIXME",
            "python": "python3",
            "modules": ["python"],
            "slurm": {
                "qos": "regular",
                "constraint": "cpu",
                "time": "00:30:00",
                "nodes": 1,
            },
        },
    }

    cluster_config = cluster_defaults.get(target, {
        "backend": "ssh",
        "ssh_host": "FIXME",
        "ssh_user": "FIXME",
        "account": "FIXME",
        "workdir": "FIXME",
        "python": "python3",
        "slurm": {
            "qos": "regular",
            "constraint": "cpu",
            "time": "00:30:00",
            "nodes": 1,
        },
    })

    remote_config = {
        "target": target,
        "clusters": {
            target: cluster_config,
        },
    }

    save_yaml(remote_config, directory / "asp-remote.yaml")
    console.print(f"[green]✓[/green] Created [cyan]asp-remote.yaml[/cyan] for {target}")


def _generate_remote_claude_section(target: str) -> str:
    """Generate the Remote Execution section for CLAUDE.md."""
    return f"""

---

## Remote Execution

This project targets **{target}** for remote execution via SSH.

### Architecture

- **SSH/SFTP** handles all remote operations: file upload, job submission (sbatch/srun),
  status queries (sacct), and result download
- Uses sshproxy certificates for NERSC authentication

### Structured Workflow (ASP CLI)

For formal analysis runs, use the ASP CLI:
```bash
asp workflow run universes/baseline.yaml    # Submit job to {target}
asp jobs list                                # List all tracked jobs
asp jobs status <job_id>                     # Check job state
asp jobs fetch <job_id>                      # Download results
```

### Environment Variable Contract

Batch scripts export these variables for `steps/main.py` to consume:
- `ASP_DECISION_{{decision_id}}` — selected option value (uppercased)
- `ASP_INPUT_{{input_id}}` — source path/URL (uppercased)
- `ASP_RESULTS_DIR` — output directory for results

### Writing steps/main.py for Remote Execution

```python
import os

# Read decisions from environment
method = os.environ["ASP_DECISION_METHOD"]

# Read inputs
data_path = os.environ["ASP_INPUT_PRIMARY_DATA"]

# Write results
results_dir = os.environ["ASP_RESULTS_DIR"]
```

### Cluster Management

```bash
asp remote setup      # Test SSH connectivity and validate config
asp remote status     # Check SSH connection status
```

### Configuration

Cluster details are in `asp-remote.yaml`. Edit ssh_user, account, and workdir
before running `asp remote setup`.
"""


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
    """Validate an ASP specification file.

    FILE can be an analysis (asp.yaml) or universe file.
    For universe files, use --analysis to specify the analysis file.

    Evidence verification (--verify-evidence) checks that quotes in insights
    actually exist in the source papers. Papers must be cached first using
    'asp paper add'.
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
    """Verify evidence for all insights.

    Args:
        insights: Dict of insight_id -> insight data.

    Raises:
        SystemExit: If any evidence verification fails.
    """
    from asp.papers.cache import PaperCache
    from asp.verification.cache import VerificationCache
    from asp.verification.core import VerificationStatus, verify_all_insights

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
            if ev_result.status == VerificationStatus.VERIFIED:
                verified_count += 1
            elif ev_result.status == VerificationStatus.CACHED:
                verified_count += 1
                cached_count += 1
            elif ev_result.status == VerificationStatus.SKIPPED:
                skipped_count += 1
            else:
                failed_count += 1
                has_errors = True
                status_icon = "[red]✗[/red]"
                if ev_result.status == VerificationStatus.ERROR:
                    status_icon = "[yellow]![/yellow]"

                console.print(
                    f"  {status_icon} [{insight_id}] {ev_result.evidence_id}: {ev_result.message}"
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
        console.print("  3. Ensure the paper is cached: asp paper add <doi>")
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
@click.option("--cwl", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--outdir", type=click.Path(path_type=Path), help="Output directory")
@click.option("--quiet", "-q", is_flag=True, help="Suppress cwltool progress output")
@click.option("--local", is_flag=True, help="Force local execution even if asp-remote.yaml exists")
def workflow_run(
    universe_file: Path,
    cwl: Path | None,
    analysis: Path | None,
    outdir: Path | None,
    quiet: bool,
    local: bool,
) -> None:
    """Run a workflow with parameters from a universe.

    If asp-remote.yaml exists, submits to the remote cluster via SSH.
    Otherwise (or with --local), runs locally using cwltool (requires --cwl).

    Examples:
        asp workflow run universes/baseline.yaml --cwl workflows/main.cwl
        asp workflow run universes/baseline.yaml            # remote if configured
        asp workflow run universes/baseline.yaml --local    # force local
    """
    analysis_path = _require_analysis(analysis, universe_file.parent)
    spec = load_yaml(analysis_path)
    uni = load_yaml(universe_file)
    project_dir = analysis_path.parent

    # Check for remote config
    remote_config_path = project_dir / "asp-remote.yaml"
    if remote_config_path.exists() and not local:
        _workflow_run_remote(spec, uni, universe_file, analysis_path, project_dir)
    else:
        if cwl is None:
            console.print(
                "[red]Error:[/red] --cwl is required for local execution. "
                "Provide a CWL workflow file."
            )
            raise SystemExit(1)
        _workflow_run_local(spec, uni, universe_file, cwl, analysis_path, outdir, quiet)


def _workflow_run_local(
    spec: dict[str, Any],
    uni: dict[str, Any],
    universe_file: Path,
    cwl: Path,
    analysis_path: Path,
    outdir: Path | None,
    quiet: bool,
) -> None:
    """Run a CWL workflow locally using cwltool."""
    import tempfile

    from asp.workflow.mapping import resolve_inputs

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

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Print stdout/stderr to console
        if result.stderr:
            console.print(result.stderr, end="")
        if result.stdout:
            console.print(result.stdout, end="")

        if result.returncode != 0:
            raise SystemExit(result.returncode)

        console.print()
        console.print("[green]✓[/green] Workflow completed successfully")

        if outdir:
            console.print(f"[dim]Outputs in:[/dim] {outdir}")

    finally:
        # Clean up temp file
        params_file.unlink(missing_ok=True)


def _upload_via_ssh(
    client: Any,
    project_dir: Path,
    remote_job_dir: str,
    script: str,
) -> None:
    """Upload steps/ and batch script to the cluster via the SSH client."""
    from asp.remote.client import _sftp_makedirs, _sftp_upload_dir

    console.print("[dim]Uploading files via SSH...[/dim]")
    ssh_client = client._get_client()
    sftp = ssh_client.open_sftp()
    try:
        # Create remote job directory
        _sftp_makedirs(sftp, remote_job_dir)

        # Upload batch script
        with sftp.file(f"{remote_job_dir}/job.sh", "w") as f:
            f.write(script)

        # Upload steps/ directory
        steps_dir = project_dir / "steps"
        if steps_dir.exists():
            _sftp_upload_dir(sftp, steps_dir, f"{remote_job_dir}/steps")

        sftp.close()
        console.print("[green]✓[/green] Files uploaded")
    finally:
        pass


def _workflow_run_remote(
    spec: dict[str, Any],
    uni: dict[str, Any],
    universe_file: Path,
    analysis_path: Path,
    project_dir: Path,
) -> None:
    """Submit a workflow to a remote cluster via SSH."""
    from asp.remote.client import get_client, load_remote_config
    from asp.remote.jobs import JobHandle, JobRegistry
    from asp.remote.script_gen import generate_batch_script

    config = load_remote_config(project_dir)
    target = config.get("target", "unknown")
    cluster_config = config.get("clusters", {}).get(target, {})
    universe_id = uni.get("id", universe_file.stem)

    console.print(f"[dim]Universe:[/dim] {universe_file.name}")
    console.print(f"[dim]Target:[/dim] {target}")
    console.print()

    # Generate batch script
    workdir = cluster_config.get("workdir", "/tmp")
    remote_job_dir = f"{workdir}/jobs/{universe_id}"
    script = generate_batch_script(spec, uni, cluster_config, remote_job_dir)

    console.print(f"[dim]Remote workdir:[/dim] {remote_job_dir}")

    # Get SSH client
    client = get_client(project_dir)

    # Upload steps/ and batch script via SFTP
    _upload_via_ssh(client, project_dir, remote_job_dir, script)

    # Submit via SSH
    slurm_config = cluster_config.get("slurm", {})
    qos = slurm_config.get("qos", "regular")

    if qos == "interactive":
        # Interactive QOS: use srun (blocks until completion)
        console.print("[dim]Running job interactively via srun...[/dim]")
        slurm_args = []
        if slurm_config.get("qos"):
            slurm_args += ["--qos", slurm_config["qos"]]
        if cluster_config.get("account"):
            slurm_args += ["--account", cluster_config["account"]]
        if slurm_config.get("constraint"):
            slurm_args += ["--constraint", slurm_config["constraint"]]
        if slurm_config.get("time"):
            slurm_args += ["--time", slurm_config["time"]]
        if slurm_config.get("nodes"):
            slurm_args += ["--nodes", str(slurm_config["nodes"])]

        result = client.run_interactive(f"{remote_job_dir}/job.sh", slurm_args)
        rc = int(result.get("returncode", "1"))
        if result.get("stdout"):
            console.print(result["stdout"].rstrip())
        if result.get("stderr"):
            console.print(f"[dim]{result['stderr'].rstrip()}[/dim]")

        if rc == 0:
            console.print(f"\n[green]✓[/green] Job completed successfully")
        else:
            console.print(f"\n[red]✗[/red] Job failed (exit code {rc})")
    else:
        # Batch QOS: use sbatch (async, track with jobs commands)
        console.print("[dim]Submitting job...[/dim]")
        remote_job_id = client.submit_batch(f"{remote_job_dir}/job.sh")

        # Save to registry
        analysis_name = spec.get("analysis", {}).get("name", "")
        job = JobHandle.create(
            cluster=target,
            universe_id=universe_id,
            remote_job_id=remote_job_id,
            workdir=remote_job_dir,
            analysis_name=analysis_name,
        )

        registry = JobRegistry(project_dir)
        registry.add(job)

        console.print()
        console.print(f"[green]✓[/green] Job submitted: [cyan]{job.job_id}[/cyan]")
        console.print(f"[dim]Slurm job ID:[/dim] {remote_job_id}")
        console.print(f"\nTrack with: [cyan]asp jobs status {job.job_id}[/cyan]")


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
        asp paper add 10.48550/arXiv.1706.03762 --version 7
        asp paper add 10.1038/s41586-023-06221-2
        asp paper add 10.1234/example --pdf ./local_paper.pdf
    """
    from asp.papers.cache import PaperCache
    from asp.papers.download import download_paper

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
    from asp.papers.cache import PaperCache

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
    from asp.papers.cache import PaperCache

    cache = PaperCache()
    paper = cache.get(doi, version)

    if not paper:
        console.print(f"[red]Error:[/red] Paper not found in cache: {doi}")
        if version:
            console.print(f"  (version {version})")
        console.print("\nUse [cyan]asp paper add[/cyan] to download the paper first.")
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
    from asp.papers.cache import PaperCache

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
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def paper_remove(doi: str, version: int | None, yes: bool) -> None:
    """Remove a paper from the cache."""
    from asp.papers.cache import PaperCache

    cache = PaperCache()

    if not cache.has(doi, version):
        console.print(f"[red]Error:[/red] Paper not found: {doi}")
        raise SystemExit(1)

    if not yes:
        if not click.confirm(f"Remove paper {doi} from cache?"):
            console.print("Aborted.")
            return

    cache.remove(doi, version)
    console.print("[green]✓[/green] Paper removed from cache")


@paper.command("fetch-metadata")
@click.argument("doi", required=False)
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch metadata for all cached papers")
def paper_fetch_metadata(doi: str | None, version: int | None, fetch_all: bool) -> None:
    """Fetch metadata (title, authors) for cached papers.

    Uses DOI content negotiation to retrieve metadata from DOI.org.
    This works for any DOI (Crossref, DataCite, arXiv, etc.).

    Examples:

        asp paper fetch-metadata 10.48550/arXiv.1706.03762

        asp paper fetch-metadata --all
    """
    from asp.papers.cache import PaperCache
    from asp.papers.download import fetch_doi_metadata

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
                # Already has metadata
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
    verifies all quotes against it, making this much more efficient than
    calling verify-quote multiple times.

    Input format (stdin):
        {"quotes": [{"text": "...", "page": N, "prefix": "...", "suffix": "..."}, ...]}

    Output format (stdout, JSON):
        {"doi": "...", "results": [...], "summary": {...}}

    Exit codes:
      0 - All quotes verified
      1 - Some quotes not found
      2 - Error (paper not cached, invalid input, etc.)

    Examples:
        echo '{"quotes": [{"text": "Attention is all you need"}]}' | \\
            asp paper verify-quotes 10.48550/arXiv.1706.03762 --version 7

        cat quotes.json | asp paper verify-quotes 10.1038/s41586-023-06221-2
    """
    from asp.papers.cache import PaperCache
    from asp.verification.core import VerificationStatus, verify_quote_in_pdf
    from asp.verification.pdf import extract_text_from_pdf

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

    # Extract text from PDF (ONCE - this is the key optimization)
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

    # Verify each quote against the already-extracted PDF text
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

        # Truncate quote for display
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

    # Exit code based on results
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

    Examples:
        asp paper verify-quote 10.48550/arXiv.1706.03762 \\
          --quote "Attention is all you need" --version 7

        asp paper verify-quote 10.1038/s41586-023-06221-2 \\
          --quote "exact text from paper" --page 5 --json
    """
    from asp.papers.cache import PaperCache
    from asp.verification.core import VerificationStatus, verify_quote_in_pdf
    from asp.verification.pdf import extract_text_from_pdf

    cache = PaperCache()
    cached_paper = cache.get(doi, version)

    if not cached_paper:
        # Error: paper not cached
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
            console.print("Use [cyan]asp paper add[/cyan] first.")
        raise SystemExit(2)

    # Extract text from PDF
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

    # Verify the quote
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

    # Exit code based on status
    if status == VerificationStatus.VERIFIED:
        raise SystemExit(0)
    else:
        raise SystemExit(1)


# =============================================================================
# Navigator command
# =============================================================================


def _get_asp_config_path() -> Path:
    """Get the path to the ASP global config file."""
    return Path.home() / ".asp" / "config.yaml"


def _load_asp_config() -> dict[str, Any]:
    """Load ASP global config from ~/.asp/config.yaml."""
    config_path = _get_asp_config_path()
    if not config_path.exists():
        return {}
    return load_yaml(config_path)


def _save_asp_config(config: dict[str, Any]) -> None:
    """Save ASP global config to ~/.asp/config.yaml."""
    config_path = _get_asp_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(config, config_path)


def _get_navigator_path() -> Path | None:
    """Get Navigator path from config or environment variable."""
    # Check environment variable first
    env_path = Path(p) if (p := __import__("os").environ.get("ASP_NAVIGATOR_PATH")) else None
    if env_path and env_path.exists():
        return env_path

    # Check config file
    config = _load_asp_config()
    config_path = config.get("navigator", {}).get("path")
    if config_path:
        path = Path(config_path)
        if path.exists():
            return path

    return None


@main.command()
@click.argument("target", default=".")
@click.option("--port", default=8080, type=int, help="Port to serve on")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
@click.option("--jupyter", is_flag=True, help="Print JupyterHub proxied URL")
def canvas(target: str, port: int, no_browser: bool, jupyter: bool) -> None:
    """Open the ASP Canvas visual editor.

    Launches a Python-served web UI for visualizing and interacting with
    ASP projects. No Node.js required.

    Install with: pip install asp[canvas]

    Examples:

        asp canvas                     # Open current project

        asp canvas /some/path          # Open specific project

        asp canvas --port 9000         # Custom port

        asp canvas --jupyter           # Print JupyterHub proxied URL
    """
    try:
        from asp_canvas.cli import main as canvas_main
    except ImportError:
        console.print("[red]Error:[/red] Canvas not installed.")
        console.print("  Install with: [cyan]pip install asp[canvas][/cyan]")
        raise SystemExit(1)

    # Build args list for the canvas CLI
    args = [target]
    if port != 8080:
        args.extend(["--port", str(port)])
    if no_browser:
        args.append("--no-browser")
    if jupyter:
        args.append("--jupyter")

    canvas_main(args, standalone_mode=False)


@main.command()
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    help="Project path (default: current directory)",
)
@click.option(
    "--configure",
    is_flag=True,
    help="Reconfigure Navigator path",
)
def navigator(path: Path | None, configure: bool) -> None:
    """Open the current project in Navigator.

    Navigator is the visual canvas editor for ASP projects. This command
    starts Navigator for the current project.

    Press Ctrl+C to stop Navigator.

    First-time setup will prompt for the Navigator installation path.

    Examples:

        asp navigator                  # Open current project

        asp navigator -p /some/path    # Open specific project

        asp navigator --configure      # Reconfigure Navigator path
    """
    # Get or configure Navigator path
    navigator_path = _get_navigator_path()

    if configure or navigator_path is None:
        # Prompt for Navigator path
        if navigator_path is None:
            console.print("[yellow]Navigator path not configured.[/yellow]")
        default_hint = navigator_path or ""
        user_path = click.prompt(
            "Where is Navigator installed?",
            default=str(default_hint) if default_hint else None,
            type=click.Path(exists=True, path_type=Path),
        )
        navigator_path = Path(user_path)

        # Validate it looks like Navigator
        if not (navigator_path / "package.json").exists():
            console.print(f"[red]Error:[/red] {navigator_path} doesn't look like Navigator")
            console.print("  (No package.json found)")
            raise SystemExit(1)

        # Save to config
        config = _load_asp_config()
        if "navigator" not in config:
            config["navigator"] = {}
        config["navigator"]["path"] = str(navigator_path)
        _save_asp_config(config)
        console.print(f"[green]✓[/green] Saved Navigator path to ~/.asp/config.yaml")

        if configure:
            return

    # Find the ASP project to open
    if path is None:
        path = Path.cwd()

    # Verify it's an ASP project
    analysis_file = find_analysis_file(path)
    if analysis_file is None:
        console.print(f"[red]Error:[/red] No asp.yaml found in {path}")
        raise SystemExit(1)

    project_path = analysis_file.parent.resolve()
    # URL-encode the path for the query parameter
    from urllib.parse import quote
    url = f"http://localhost:3000?project={quote(str(project_path), safe='')}"

    # Run Navigator in foreground (Ctrl+C to stop)
    console.print(f"[bold]Starting Navigator for:[/bold] {project_path}")
    console.print()
    console.print("[bold green]Open this URL in your browser:[/bold green]")
    console.print(f"  {url}")
    console.print()
    console.print("[dim]Press Ctrl+C to stop (ignore the localhost:3000 URL below)[/dim]\n")

    try:
        subprocess.run(
            ["npm", "run", "dev:all"],
            cwd=navigator_path,
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Navigator stopped[/dim]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Navigator exited with code {e.returncode}")
        raise SystemExit(e.returncode)


# =============================================================================
# Remote cluster commands
# =============================================================================


@main.group()
def remote() -> None:
    """Remote cluster management commands."""
    pass


@remote.command("setup")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def remote_setup(analysis: Path | None) -> None:
    """Test SSH connectivity and validate remote cluster config.

    Verifies that asp-remote.yaml is configured correctly and that
    SSH can connect to the cluster login node.

    Prerequisites:
        1. Edit asp-remote.yaml with your username, account, and workdir
        2. Run sshproxy.sh to get a 24-hour SSH certificate
    """
    from asp.remote.bootstrap import check_ssh
    from asp.remote.client import load_remote_config

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    config = load_remote_config(project_dir)
    target = config.get("target", "")
    cluster_config = config.get("clusters", {}).get(target, {})

    if not cluster_config:
        console.print(f"[red]Error:[/red] No cluster config for '{target}' in asp-remote.yaml")
        raise SystemExit(1)

    if cluster_config.get("ssh_user") == "FIXME":
        console.print("[red]Error:[/red] Edit asp-remote.yaml first — set ssh_user, account, workdir")
        raise SystemExit(1)

    console.print(f"[bold]Testing SSH connection to {target}...[/bold]")
    console.print()

    host = cluster_config.get("ssh_host", "")
    user = cluster_config.get("ssh_user", "")
    console.print(f"[dim]Host:[/dim] {host}")
    console.print(f"[dim]User:[/dim] {user}")

    try:
        ok = check_ssh(cluster_config)
    except FileNotFoundError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise SystemExit(1)

    if ok:
        console.print(f"\n[green]✓[/green] SSH connection to {target} successful")
        console.print(f"\nYou can now run: [cyan]asp workflow run universes/baseline.yaml[/cyan]")
    else:
        console.print(f"\n[red]✗[/red] SSH connection to {target} failed")
        console.print("\nCheck your SSH key and config in asp-remote.yaml.")
        raise SystemExit(1)


@remote.command("status")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def remote_status(analysis: Path | None) -> None:
    """Check SSH connectivity to the remote cluster."""
    from asp.remote.bootstrap import check_ssh
    from asp.remote.client import load_remote_config

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    config = load_remote_config(project_dir)
    target = config.get("target", "")
    cluster_config = config.get("clusters", {}).get(target, {})

    host = cluster_config.get("ssh_host", "")
    user = cluster_config.get("ssh_user", "")
    console.print(f"[dim]Host:[/dim] {host}")
    console.print(f"[dim]User:[/dim] {user}")
    console.print(f"[dim]Cluster:[/dim] {target}")

    if check_ssh(cluster_config):
        console.print("[green]✓[/green] SSH connection is working")
    else:
        console.print("[red]✗[/red] SSH connection failed")
        console.print("\nCheck your SSH key and config in asp-remote.yaml.")
        raise SystemExit(1)


# =============================================================================
# Jobs commands
# =============================================================================


@main.group()
def jobs() -> None:
    """Job tracking commands for remote execution."""
    pass


@jobs.command("list")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def jobs_list(analysis: Path | None) -> None:
    """List all tracked remote jobs."""
    from asp.remote.jobs import JobRegistry

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    registry = JobRegistry(project_dir)
    all_jobs = registry.list_jobs()

    if not all_jobs:
        console.print("[dim]No jobs tracked yet[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Job ID", no_wrap=True)
    table.add_column("Universe", no_wrap=True)
    table.add_column("Cluster", no_wrap=True)
    table.add_column("Slurm ID", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Submitted", no_wrap=True)

    for job in all_jobs:
        status_style = {
            "PENDING": "[yellow]PENDING[/yellow]",
            "RUNNING": "[blue]RUNNING[/blue]",
            "COMPLETED": "[green]COMPLETED[/green]",
            "FAILED": "[red]FAILED[/red]",
            "CANCELLED": "[dim]CANCELLED[/dim]",
        }.get(job.status, job.status)

        submitted = job.submitted_at[:19] if job.submitted_at else "-"
        table.add_row(
            job.job_id,
            job.universe_id,
            job.cluster,
            job.remote_job_id,
            status_style,
            submitted,
        )

    console.print(table)
    console.print(f"\n[dim]{len(all_jobs)} job(s)[/dim]")


@jobs.command("status")
@click.argument("job_id")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def jobs_status(job_id: str, analysis: Path | None) -> None:
    """Check and update the status of a remote job."""
    from asp.remote.client import get_client
    from asp.remote.jobs import JobRegistry

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    registry = JobRegistry(project_dir)
    job = registry.get(job_id)

    if not job:
        console.print(f"[red]Error:[/red] Job not found: {job_id}")
        raise SystemExit(1)

    console.print(f"[dim]Job:[/dim] {job.job_id}")
    console.print(f"[dim]Universe:[/dim] {job.universe_id}")
    console.print(f"[dim]Cluster:[/dim] {job.cluster}")
    console.print(f"[dim]Slurm ID:[/dim] {job.remote_job_id}")
    console.print(f"[dim]Workdir:[/dim] {job.workdir}")

    # Query live status from the cluster
    if job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
        try:
            client = get_client(project_dir)
            state = client.job_status(job.remote_job_id)
            new_status = str(state)
            if new_status != job.status:
                registry.update_status(job.job_id, new_status)
                job.status = new_status
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not query live status: {e}")

    status_display = {
        "PENDING": "[yellow]PENDING[/yellow]",
        "RUNNING": "[blue]RUNNING[/blue]",
        "COMPLETED": "[green]COMPLETED[/green]",
        "FAILED": "[red]FAILED[/red]",
        "CANCELLED": "[dim]CANCELLED[/dim]",
    }.get(job.status, job.status)

    console.print(f"\n[bold]Status:[/bold] {status_display}")

    if job.status == "COMPLETED":
        console.print(f"\nFetch results with: [cyan]asp jobs fetch {job.job_id}[/cyan]")


@jobs.command("fetch")
@click.argument("job_id")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--outdir", type=click.Path(path_type=Path), help="Local output directory")
def jobs_fetch(job_id: str, analysis: Path | None, outdir: Path | None) -> None:
    """Download results for a completed remote job."""
    from asp.remote.client import get_client
    from asp.remote.jobs import JobRegistry

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    registry = JobRegistry(project_dir)
    job = registry.get(job_id)

    if not job:
        console.print(f"[red]Error:[/red] Job not found: {job_id}")
        raise SystemExit(1)

    if job.status not in ("COMPLETED", "RUNNING", "UNKNOWN"):
        console.print(f"[yellow]Warning:[/yellow] Job status is {job.status}")
        if not click.confirm("Fetch results anyway?"):
            return

    # Default output directory
    if outdir is None:
        outdir = project_dir / "results" / job.universe_id

    outdir.mkdir(parents=True, exist_ok=True)

    remote_results = f"{job.workdir}/results"
    console.print(f"[dim]Downloading:[/dim] {remote_results}")
    console.print(f"[dim]To:[/dim] {outdir}")

    try:
        client = get_client(project_dir)
        client.download(remote_results, outdir)
        console.print(f"\n[green]✓[/green] Results downloaded to [cyan]{outdir}[/cyan]")
    except Exception as e:
        console.print(f"[red]Error:[/red] Download failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
