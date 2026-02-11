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
    help="Remote cluster target (e.g., perlmutter). Copies config from ~/.asp/remotes/.",
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
        console.print("  2. Run [cyan]asp remote status[/cyan] to verify SSH connectivity")
        console.print("  3. Run [cyan]claude[/cyan] and use [cyan]/asp:new[/cyan]")
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
    allow_rules = [
        "Bash(asp:*)",
        "Bash(cwltool:*)",
        "Edit",
        "WebSearch",
        "WebFetch",
    ]

    # For remote-targeted projects, don't auto-allow python/pip — the
    # PreToolUse hook will block them with a helpful redirect message.
    # For local projects, allow python freely.
    if not target:
        allow_rules.insert(1, "Bash(python:*)")

    settings: dict[str, Any] = {
        "permissions": {
            "allow": allow_rules,
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

    # For remote-targeted projects, add a PreToolUse hook that blocks
    # direct python/pip execution and redirects to "asp remote exec".
    if target:
        settings["hooks"]["PreToolUse"] = [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": ".claude/scripts/block-local-exec.sh",
                        "timeout": 3,
                    },
                ],
            },
        ]

    settings_file = claude_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2) + "\n")


def _create_remote_config(directory: Path, target: str) -> None:
    """Copy remote config from ~/.asp/remotes/ into the project.

    Requires that 'asp remote setup' has been run first to create
    the global config at ~/.asp/remotes/{target}.yaml.
    """
    registry = _get_cluster_registry()
    if target not in registry:
        supported = ", ".join(sorted(registry))
        console.print(
            f"[red]Error:[/red] Unsupported cluster: {target}. "
            f"Supported: {supported}"
        )
        raise SystemExit(1)

    global_config = Path.home() / ".asp" / "remotes" / f"{target}.yaml"
    if not global_config.exists():
        console.print(
            f"[red]Error:[/red] No config found for {target}. "
            f"Run [cyan]asp remote setup[/cyan] first to configure {target}."
        )
        raise SystemExit(1)

    # Load config and append project name to workdir so each project
    # gets its own subdirectory on the remote cluster.
    config = load_yaml(global_config)
    project_name = directory.resolve().name
    target_name = config.get("target", target)
    cluster_cfg = config.get("clusters", {}).get(target_name, {})
    base_workdir = cluster_cfg.get("workdir", "")
    if base_workdir and not base_workdir.endswith(f"/{project_name}"):
        cluster_cfg["workdir"] = f"{base_workdir.rstrip('/')}/{project_name}"

    save_yaml(config, directory / "remote.yaml")
    console.print(f"[green]✓[/green] Created [cyan]remote.yaml[/cyan] from {global_config}")
    if base_workdir != cluster_cfg.get("workdir"):
        console.print(f"  [dim]workdir:[/dim] {cluster_cfg['workdir']}")


def _generate_remote_claude_section(target: str) -> str:
    """Generate the Remote Execution section for CLAUDE.md.

    Reads from templates/CLAUDE-remote.md and substitutes {{target}}.
    """
    plugin_source = _get_plugin_source_dir()
    template_path = plugin_source / "templates" / "CLAUDE-remote.md" if plugin_source else None

    if template_path and template_path.exists():
        content = template_path.read_text()
        return content.replace("{{target}}", target)

    # Fallback if template not found
    return f"\n\n---\n\n## Remote Execution\n\nThis project targets **{target}** via SSH.\n"


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
    """Run a CWL workflow locally with parameters from a universe.

    Generates CWL parameters (including input files) from the universe
    and executes the workflow using cwltool.

    For remote execution, use 'asp remote' commands instead.

    Example:
        asp workflow run universes/baseline.yaml --cwl workflows/main.cwl
    """
    analysis_path = _require_analysis(analysis, universe_file.parent)
    spec = load_yaml(analysis_path)
    uni = load_yaml(universe_file)
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


def _get_cluster_registry() -> dict[str, dict[str, Any]]:
    """Load the cluster registry from YAML files in asp/remote/clusters/."""
    from asp.remote.clusters import load_cluster_registry

    return load_cluster_registry()


@remote.command("setup")
@click.argument("cluster", default=None, required=False)
def remote_setup(cluster: str | None) -> None:
    """Interactive one-time setup for a remote cluster (global).

    Prompts for credentials, installs SSH tooling if needed,
    generates certificates, tests connectivity, and saves the
    config to ~/.asp/remotes/ for reuse across projects.

    This runs outside any project. To test connectivity inside a
    project, use 'asp remote status'.

    If CLUSTER is not specified, shows a list of available clusters to choose from.

    Example:
        asp remote setup
        asp remote setup perlmutter
        asp init my-analysis --target perlmutter
    """
    import platform
    import tempfile
    import urllib.request

    from asp.helpers import save_yaml

    registry = _get_cluster_registry()

    # If no cluster specified, let the user pick
    if cluster is None:
        cluster_ids = sorted(registry)
        console.print("\n[bold]Available clusters:[/bold]\n")
        for i, cid in enumerate(cluster_ids, 1):
            label = registry[cid].get("label", cid)
            console.print(f"  {i}. {label} ([cyan]{cid}[/cyan])")
        console.print()
        choice = click.prompt(
            "Select a cluster",
            type=click.IntRange(1, len(cluster_ids)),
            default=1,
        )
        cluster = cluster_ids[choice - 1]

    if cluster not in registry:
        supported = ", ".join(sorted(registry))
        console.print(
            f"[red]Error:[/red] Unknown cluster: {cluster}. "
            f"Supported: {supported}"
        )
        raise SystemExit(1)

    spec = registry[cluster]
    console.print(f"\n[bold]Setting up {spec['label']}[/bold]\n")

    # 1. Prompt for credentials
    prompts = spec["prompts"]
    username = click.prompt(prompts["username"], type=str).strip()
    if not username:
        console.print("[red]Error:[/red] Username is required")
        raise SystemExit(1)

    account = click.prompt(prompts["account"], type=str).strip()
    if not account:
        console.print("[red]Error:[/red] Account is required")
        raise SystemExit(1)

    first_letter = username[0]
    default_workdir = spec["default_workdir"].format(
        first_letter=first_letter, username=username
    )
    workdir = click.prompt(prompts["workdir"], default=default_workdir, type=str).strip()

    # 2. Check/install sshproxy (if cluster uses it)
    sshproxy_spec = spec.get("sshproxy")
    sshproxy_path = None
    ssh_cert = Path(spec["ssh_key"])

    if sshproxy_spec:
        console.print("\n[bold]Checking sshproxy...[/bold]")
        sshproxy_path = shutil.which("sshproxy")

        if sshproxy_path:
            console.print(f"[green]✓[/green] sshproxy found at {sshproxy_path}")
        else:
            console.print("[yellow]sshproxy not found.[/yellow] Installing...")
            system = platform.system()
            machine = platform.machine()
            download_page = sshproxy_spec["download_page"]

            if system == "Darwin":
                pkg_url = sshproxy_spec["macos_pkg"]
                console.print(f"\n[dim]Downloading {pkg_url}...[/dim]")
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as tmp:
                        urllib.request.urlretrieve(pkg_url, tmp.name)
                        tmp_pkg = tmp.name
                    console.print("[dim]Launching macOS installer...[/dim]")
                    subprocess.run(["open", tmp_pkg], check=True)
                    click.pause("Press Enter after the installer finishes...")
                except Exception as e:
                    console.print(f"[red]Error downloading/installing sshproxy:[/red] {e}")
                    console.print(f"\nDownload manually from: {download_page}")
                    raise SystemExit(1)
            elif system == "Linux":
                if "aarch64" in machine or "arm64" in machine:
                    tar_url = sshproxy_spec["linux_aarch64"]
                else:
                    tar_url = sshproxy_spec["linux_x86_64"]

                local_bin = Path.home() / ".local" / "bin"
                local_bin.mkdir(parents=True, exist_ok=True)
                console.print(f"\n[dim]Downloading {tar_url}...[/dim]")
                try:
                    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                        urllib.request.urlretrieve(tar_url, tmp.name)
                        tmp_tar = tmp.name
                    subprocess.run(
                        ["tar", "xzf", tmp_tar, "-C", str(local_bin)],
                        check=True,
                        capture_output=True,
                    )
                    console.print(f"[green]✓[/green] Installed sshproxy to {local_bin}")
                except Exception as e:
                    console.print(f"[red]Error downloading/installing sshproxy:[/red] {e}")
                    console.print(f"\nDownload manually from: {download_page}")
                    raise SystemExit(1)
            else:
                console.print(f"[red]Error:[/red] Unsupported platform: {system}")
                console.print(f"Download sshproxy manually from: {download_page}")
                raise SystemExit(1)

            # Re-check
            sshproxy_path = shutil.which("sshproxy")
            if not sshproxy_path:
                console.print(
                    "[yellow]Warning:[/yellow] sshproxy not found on PATH after install. "
                    "You may need to restart your shell or add ~/.local/bin to PATH."
                )

        # 3. Check/generate SSH certificate
        if ssh_cert.exists():
            console.print(f"\n[green]✓[/green] SSH certificate found at {ssh_cert}")
        else:
            console.print("\n[bold]Generating SSH certificate...[/bold]")
            sshproxy_cmd = sshproxy_path or "sshproxy"
            console.print(f"[dim]Running: {sshproxy_cmd} -u {username}[/dim]")
            console.print("[dim]You will be prompted for your Password+OTP.[/dim]\n")
            try:
                result = subprocess.run(
                    [sshproxy_cmd, "-u", username],
                    check=False,
                )
                if result.returncode != 0:
                    console.print("\n[red]Error:[/red] sshproxy failed. Check your credentials.")
                    raise SystemExit(1)
            except FileNotFoundError:
                console.print("[red]Error:[/red] sshproxy command not found.")
                raise SystemExit(1)

            if ssh_cert.exists():
                console.print(f"\n[green]✓[/green] SSH certificate created at {ssh_cert}")
            else:
                console.print(
                    "\n[yellow]Warning:[/yellow] Certificate file not found after sshproxy."
                )

    # 4. Test SSH connectivity
    console.print(f"\n[bold]Testing SSH connection to {cluster}...[/bold]")
    cluster_config = {
        "ssh_host": spec["ssh_host"],
        "ssh_user": username,
        "ssh_key": str(ssh_cert),
    }

    try:
        from asp.remote.bootstrap import check_ssh

        ok = check_ssh(cluster_config)
    except Exception as e:
        console.print(f"\n[yellow]Warning:[/yellow] SSH test failed: {e}")
        ok = False

    if ok:
        console.print(f"[green]✓[/green] SSH connection to {cluster} successful")
    else:
        console.print(f"[yellow]Warning:[/yellow] SSH connection test failed.")
        console.print("The config will still be saved. You may need to run sshproxy again.")

    # 5. Save config to ~/.asp/remotes/
    remotes_dir = Path.home() / ".asp" / "remotes"
    remotes_dir.mkdir(parents=True, exist_ok=True)
    config_path = remotes_dir / f"{cluster}.yaml"

    remote_config = {
        "target": cluster,
        "clusters": {
            cluster: {
                "backend": "ssh",
                "ssh_host": spec["ssh_host"],
                "ssh_user": username,
                "ssh_key": str(ssh_cert),
                "account": account,
                "workdir": workdir,
                "python": spec.get("python", "python3"),
                "modules": spec.get("modules", []),
                "slurm": spec.get("slurm_defaults", {}),
            },
        },
    }

    save_yaml(remote_config, config_path)
    console.print(f"\n[green]✓[/green] Saved config to [cyan]{config_path}[/cyan]")
    console.print(f"\nNext: [cyan]asp init my-project --target {cluster}[/cyan]")


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

    try:
        ok = check_ssh(cluster_config)
    except Exception as e:
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1)

    if ok:
        console.print("[green]✓[/green] SSH connection is working")
    else:
        console.print("[red]✗[/red] SSH connection failed")
        console.print("\nCheck your SSH key and config in remote.yaml.")
        raise SystemExit(1)


@remote.command("exec")
@click.argument("command", nargs=-1, required=True)
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("--push", is_flag=True, help="Push local files before executing.")
def remote_exec(command: tuple[str, ...], analysis: Path | None, push: bool) -> None:
    """Run a command on the remote cluster.

    Use --push to sync local files before execution.
    """
    from asp.remote.session import RemoteSession

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent

    with RemoteSession(project_dir) as session:
        if push:
            console.print("[dim]Pushing local files...[/dim]")
            pushed = session.push_project()
            console.print(f"[dim]Pushed {len(pushed)} items to {session.target}[/dim]")

        cmd_str = " ".join(command)
        console.print(f"[dim]$ {cmd_str}[/dim]")
        stdout, stderr, exit_code = session.exec(cmd_str)

        if stdout:
            console.print(stdout, end="")
        if stderr:
            console.print(f"[yellow]{stderr}[/yellow]", end="")

        if exit_code != 0:
            console.print(f"\n[red]Exit code: {exit_code}[/red]")

    raise SystemExit(exit_code)


@remote.command("push")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
def remote_push(analysis: Path | None) -> None:
    """Push local project files to the remote cluster."""
    from asp.remote.session import RemoteSession

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent

    with RemoteSession(project_dir) as session:
        pushed = session.push_project()
        console.print(f"[green]✓[/green] Pushed {len(pushed)} items to {session.target}")
        for item in pushed:
            console.print(f"  [dim]{item}[/dim]")


@remote.command("pull")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("--job-id", help="Pull results for a specific job.")
@click.option("--universe", help="Pull results for a specific universe.")
def remote_pull(analysis: Path | None, job_id: str | None, universe: str | None) -> None:
    """Pull results from the remote cluster."""
    from asp.remote.session import RemoteSession

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent

    with RemoteSession(project_dir) as session:
        local_path = session.pull_results(universe_id=universe, job_id=job_id)
        console.print(f"[green]✓[/green] Results downloaded to {local_path}")


@remote.command("submit")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("--script", type=click.Path(exists=True, path_type=Path), help="Local batch script.")
@click.option("--universe", default="default", help="Universe ID for job tracking.")
def remote_submit(
    analysis: Path | None, script: Path | None, universe: str,
) -> None:
    """Submit a batch job to the remote cluster.

    Pushes project files, writes the batch script to the remote, and submits via sbatch.
    """
    from asp.remote.session import RemoteSession

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent

    script_content: str | None = None
    if script:
        script_content = script.read_text()

    with RemoteSession(project_dir) as session:
        console.print(f"[dim]Submitting to {session.target}...[/dim]")
        handle = session.submit(script_content=script_content, universe_id=universe)
        console.print(f"[green]✓[/green] Job submitted")
        console.print(f"  [dim]Job ID:[/dim]  {handle.job_id}")
        console.print(f"  [dim]Slurm ID:[/dim] {handle.remote_job_id}")
        console.print(f"  [dim]Universe:[/dim] {handle.universe_id}")
        console.print(f"\nTrack with: [cyan]asp jobs list[/cyan]")
        console.print(f"Pull results: [cyan]asp remote pull --job-id {handle.job_id}[/cyan]")


@remote.command("log")
@click.argument("job_id")
@click.option("-a", "--analysis", type=click.Path(exists=True, path_type=Path))
@click.option("-n", "--lines", type=int, default=50, help="Number of lines to show (default 50).")
@click.option("--err", is_flag=True, help="Show stderr log instead of stdout.")
def remote_log(job_id: str, analysis: Path | None, lines: int, err: bool) -> None:
    """Show the Slurm log output for a remote job.

    Reads the slurm-<jobid>.out (or .err with --err) file from the remote workdir.
    """
    from asp.remote.jobs import JobRegistry
    from asp.remote.session import RemoteSession

    analysis_path = _require_analysis(analysis)
    project_dir = analysis_path.parent
    registry = JobRegistry(project_dir)
    job = registry.get(job_id)

    if not job:
        console.print(f"[red]Error:[/red] Job not found: {job_id}")
        raise SystemExit(1)

    ext = "err" if err else "out"
    workdir = job.workdir
    remote_job_id = job.remote_job_id

    with RemoteSession(project_dir) as session:
        # Find the log file matching slurm-<id>.<ext>
        log_path = f"{workdir}/slurm-{remote_job_id}.{ext}"
        stdout, stderr_out, exit_code = session.exec(f"tail -n {lines} {log_path}")

        if exit_code != 0:
            console.print(f"[red]Error:[/red] Could not read log file: {log_path}")
            if stderr_out:
                console.print(f"[dim]{stderr_out.strip()}[/dim]")
            raise SystemExit(1)

        if stdout:
            console.print(stdout, end="")
        else:
            console.print("[dim]Log file is empty[/dim]")


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
