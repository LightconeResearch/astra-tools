"""Tests for CLI commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from asp.cli import main


@pytest.fixture
def runner():
    """Return a CLI runner."""
    return CliRunner()


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_analysis(self, runner: CliRunner, minimal_analysis_path: Path):
        result = runner.invoke(main, ["validate", str(minimal_analysis_path)])
        assert result.exit_code == 0
        assert "Validation successful" in result.output

    def test_validate_valid_full_analysis(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["validate", str(full_analysis_path)])
        assert result.exit_code == 0
        assert "Validation successful" in result.output

    def test_validate_valid_universe(
        self,
        runner: CliRunner,
        baseline_universe_path: Path,
        full_analysis_path: Path,
    ):
        result = runner.invoke(
            main,
            ["validate", str(baseline_universe_path), "-a", str(full_analysis_path)],
        )
        assert result.exit_code == 0
        assert "Validation successful" in result.output

    def test_validate_invalid_analysis(self, runner: CliRunner, invalid_dir: Path):
        result = runner.invoke(main, ["validate", str(invalid_dir / "missing_version.yaml")])
        assert result.exit_code == 1
        assert "Schema validation errors" in result.output

    def test_validate_universe_without_analysis(
        self, runner: CliRunner, baseline_universe_path: Path, tmp_path: Path
    ):
        # Copy universe to temp dir where there's no asp.yaml
        import shutil

        temp_universe = tmp_path / "universes" / "test.yaml"
        temp_universe.parent.mkdir(parents=True)
        shutil.copy(baseline_universe_path, temp_universe)

        result = runner.invoke(main, ["validate", str(temp_universe)])
        assert result.exit_code == 1
        assert "requires an analysis file" in result.output

    def test_validate_nonexistent_file(self, runner: CliRunner):
        result = runner.invoke(main, ["validate", "nonexistent.yaml"])
        assert result.exit_code != 0


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_with_file(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["info", "-f", str(full_analysis_path)])
        assert result.exit_code == 0
        assert "Full Analysis" in result.output
        assert "Inputs:" in result.output
        assert "Outputs:" in result.output
        assert "Decisions:" in result.output

    def test_info_decisions_only(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["info", "-f", str(full_analysis_path), "--decisions"])
        assert result.exit_code == 0
        assert "Decisions:" in result.output
        assert "preprocessing" in result.output

    def test_info_inputs_only(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["info", "-f", str(full_analysis_path), "--inputs"])
        assert result.exit_code == 0
        assert "Inputs:" in result.output
        assert "primary_data" in result.output

    def test_info_outputs_only(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["info", "-f", str(full_analysis_path), "--outputs"])
        assert result.exit_code == 0
        assert "Outputs:" in result.output
        assert "accuracy" in result.output

    def test_info_no_file(self, runner: CliRunner, tmp_path: Path):
        # Run in a directory without asp.yaml
        result = runner.invoke(main, ["info"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "No asp.yaml found" in result.output


class TestUniverseCommands:
    """Tests for universe subcommands."""

    def test_universe_generate(self, runner: CliRunner, full_analysis_path: Path, tmp_path: Path):
        output_path = tmp_path / "generated.yaml"
        result = runner.invoke(
            main,
            [
                "universe",
                "generate",
                "-a",
                str(full_analysis_path),
                "-n",
                "test-universe",
                "-o",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert "Generated universe" in result.output
        assert output_path.exists()

    def test_universe_generate_default_output(
        self, runner: CliRunner, full_analysis_path: Path, tmp_path: Path
    ):
        import shutil

        # Copy analysis to temp dir
        temp_analysis = tmp_path / "asp.yaml"
        shutil.copy(full_analysis_path, temp_analysis)

        result = runner.invoke(
            main,
            ["universe", "generate", "-a", str(temp_analysis), "-n", "baseline"],
        )
        assert result.exit_code == 0
        assert (tmp_path / "universes" / "baseline.yaml").exists()

    def test_universe_check_valid(
        self,
        runner: CliRunner,
        baseline_universe_path: Path,
        full_analysis_path: Path,
    ):
        result = runner.invoke(
            main,
            ["universe", "check", str(baseline_universe_path), "-a", str(full_analysis_path)],
        )
        assert result.exit_code == 0
        assert "Universe is valid" in result.output

    def test_universe_check_invalid(
        self, runner: CliRunner, invalid_dir: Path, full_analysis_path: Path
    ):
        result = runner.invoke(
            main,
            [
                "universe",
                "check",
                str(invalid_dir / "universe_incompatible.yaml"),
                "-a",
                str(full_analysis_path),
            ],
        )
        assert result.exit_code == 1
        assert "validation errors" in result.output


class TestVizCommand:
    """Tests for the viz command."""

    def test_viz_ascii(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["viz", "-f", str(full_analysis_path)])
        assert result.exit_code == 0
        assert "Full Analysis" in result.output
        assert "preprocessing" in result.output

    def test_viz_mermaid(self, runner: CliRunner, full_analysis_path: Path):
        result = runner.invoke(main, ["viz", "-f", str(full_analysis_path), "--format", "mermaid"])
        assert result.exit_code == 0
        assert "graph TD" in result.output


class TestSchemaCommands:
    """Tests for schema subcommands."""

    def test_schema_export(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(main, ["schema", "export", "-o", str(tmp_path / "schemas")])
        assert result.exit_code == 0
        assert "Exported schemas" in result.output
        assert (tmp_path / "schemas" / "analysis.schema.json").exists()
        assert (tmp_path / "schemas" / "universe.schema.json").exists()

    def test_schema_show_analysis(self, runner: CliRunner):
        result = runner.invoke(main, ["schema", "show", "analysis"])
        assert result.exit_code == 0
        assert '"$defs"' in result.output or '"properties"' in result.output

    def test_schema_show_universe(self, runner: CliRunner):
        result = runner.invoke(main, ["schema", "show", "universe"])
        assert result.exit_code == 0
        assert '"properties"' in result.output


class TestVersionOption:
    """Tests for version option."""

    def test_version(self, runner: CliRunner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        # Version format: "main, version X.Y.Z" or "main, version X.Y.devN+gHASH.dDATE"
        assert "version" in result.output


class TestHelpOption:
    """Tests for help option."""

    def test_help(self, runner: CliRunner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ASP - Agentic Science Protocol CLI" in result.output

    def test_validate_help(self, runner: CliRunner):
        result = runner.invoke(main, ["validate", "--help"])
        assert result.exit_code == 0

    def test_info_help(self, runner: CliRunner):
        result = runner.invoke(main, ["info", "--help"])
        assert result.exit_code == 0

    def test_universe_help(self, runner: CliRunner):
        result = runner.invoke(main, ["universe", "--help"])
        assert result.exit_code == 0

    def test_schema_help(self, runner: CliRunner):
        result = runner.invoke(main, ["schema", "--help"])
        assert result.exit_code == 0


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_project_structure(self, runner: CliRunner, tmp_path: Path):
        """Test that basic init creates the project structure."""
        project_dir = tmp_path / "my-analysis"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert "Created ASP analysis project" in result.output

        # Check directory structure
        assert (project_dir / "asp.yaml").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "universes").is_dir()
        assert (project_dir / "universes" / "baseline.yaml").exists()
        assert (project_dir / "results").is_dir()
        assert (project_dir / "scripts").is_dir()
        assert (project_dir / "workflows").is_dir()

        # steps/ no longer created
        assert not (project_dir / "steps").exists()
        assert not (project_dir / ".asp").exists()
        assert not (project_dir / "executions").exists()

    def test_init_asp_yaml_content(self, runner: CliRunner, tmp_path: Path):
        """Test that the generated asp.yaml has the expected content."""
        project_dir = tmp_path / "content-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert (project_dir / "asp.yaml").exists()

        # Verify the file content
        content = (project_dir / "asp.yaml").read_text()
        assert "content-test" in content  # Directory name used as analysis name
        assert "version:" in content
        assert "analysis:" in content
        assert "decisions:" in content

    def test_init_gitignore_content(self, runner: CliRunner, tmp_path: Path):
        """Test gitignore content."""
        project_dir = tmp_path / "gitignore-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0

        gitignore = (project_dir / ".gitignore").read_text()
        assert "results/" in gitignore
        assert "__pycache__/" in gitignore

    def test_init_with_agent_creates_skill(self, runner: CliRunner, tmp_path: Path):
        """Test that --agent claude-code creates the skill, agents, and launches Claude."""
        from unittest.mock import patch

        project_dir = tmp_path / "agent-test"
        with patch("asp.cli.subprocess.run") as mock_run:
            result = runner.invoke(
                main,
                ["init", str(project_dir), "--agent", "claude-code", "--no-git"],
            )
        assert result.exit_code == 0
        assert "Created ASP analysis project" in result.output
        assert ".claude/" in result.output
        assert "Launching Claude Code" in result.output

        # Check skill is created
        skill_dir = project_dir / ".claude" / "skills" / "asp-analysis"
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "SCHEMA_REFERENCE.md").exists()

        # Check agent is created
        assert (project_dir / ".claude" / "agents" / "asp.md").exists()

        # Check Claude was launched with initial prompt
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "claude"
        assert "asp.md" in call_args[0][0][1]
        assert call_args[1]["cwd"] == project_dir

    def test_init_skill_content(self, runner: CliRunner, tmp_path: Path):
        """Test that the Claude Code skill and agents are created with proper content."""
        from unittest.mock import patch

        project_dir = tmp_path / "skill-test"
        with patch("asp.cli.subprocess.run"):
            result = runner.invoke(
                main,
                ["init", str(project_dir), "--agent", "claude-code", "--no-git"],
            )
        assert result.exit_code == 0

        skill_dir = project_dir / ".claude" / "skills" / "asp-analysis"
        agents_dir = project_dir / ".claude" / "agents"

        # Check SKILL.md
        skill_path = skill_dir / "SKILL.md"
        assert skill_path.exists()
        skill_content = skill_path.read_text()
        assert "name: asp-analysis" in skill_content
        assert "# ASP Analysis Skill" in skill_content
        assert "## Available Agents" in skill_content

        # Check SCHEMA_REFERENCE.md
        schema_ref_path = skill_dir / "SCHEMA_REFERENCE.md"
        assert schema_ref_path.exists()
        schema_ref_content = schema_ref_path.read_text()
        assert "# ASP Schema Reference" in schema_ref_content
        assert "## Analysis Schema" in schema_ref_content
        assert "## Universe Schema" in schema_ref_content

        # Check asp agent (combined design + experiment)
        asp_agent_path = agents_dir / "asp.md"
        assert asp_agent_path.exists()
        asp_content = asp_agent_path.read_text()
        assert "# ASP Agent" in asp_content

    def test_init_existing_nonempty_dir_decline(self, runner: CliRunner, tmp_path: Path):
        """Test declining to overwrite existing non-empty directory."""
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        (project_dir / "some_file.txt").write_text("existing content")

        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
            input="n\n",  # Decline to continue
        )
        assert result.exit_code == 0
        # asp.yaml should NOT have been created
        assert not (project_dir / "asp.yaml").exists()

    def test_init_existing_nonempty_dir_confirm(self, runner: CliRunner, tmp_path: Path):
        """Test confirming to overwrite existing non-empty directory."""
        project_dir = tmp_path / "existing-confirm"
        project_dir.mkdir()
        (project_dir / "some_file.txt").write_text("existing content")

        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
            input="y\n",  # Confirm to continue
        )
        assert result.exit_code == 0
        assert (project_dir / "asp.yaml").exists()
        # Original file should still exist
        assert (project_dir / "some_file.txt").exists()

    def test_init_current_directory(self, runner: CliRunner, tmp_path: Path):
        """Test init with default '.' directory."""
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(
                main,
                ["init", "--no-git"],
            )
            assert result.exit_code == 0
            assert (tmp_path / "asp.yaml").exists()
        finally:
            os.chdir(old_cwd)

    def test_init_generated_files_are_valid(self, runner: CliRunner, tmp_path: Path):
        """Test that generated files pass validation."""
        project_dir = tmp_path / "valid-test"
        runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )

        # Validate the generated asp.yaml
        result = runner.invoke(main, ["validate", str(project_dir / "asp.yaml")])
        assert result.exit_code == 0
        assert "Validation successful" in result.output

        # Validate the generated baseline.yaml
        result = runner.invoke(
            main,
            [
                "validate",
                str(project_dir / "universes" / "baseline.yaml"),
                "-a",
                str(project_dir / "asp.yaml"),
            ],
        )
        assert result.exit_code == 0
        assert "Validation successful" in result.output

    def test_init_with_git(self, runner: CliRunner, tmp_path: Path):
        """Test that git is initialized by default (when --no-git not passed)."""
        project_dir = tmp_path / "git-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir)],
        )
        assert result.exit_code == 0

        # Git directory should exist (if git is available)
        if (project_dir / ".git").exists():
            assert "Initialized git repository" in result.output

    def test_init_no_git_flag(self, runner: CliRunner, tmp_path: Path):
        """Test that --no-git flag prevents git initialization."""
        project_dir = tmp_path / "no-git-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        # Git directory should NOT exist
        assert not (project_dir / ".git").exists()

