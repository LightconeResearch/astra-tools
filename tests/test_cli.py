"""Tests for CLI commands."""

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from astra.cli import main


@pytest.fixture
def runner() -> CliRunner:
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
        assert "validation errors" in result.output

    def test_validate_universe_without_analysis(
        self, runner: CliRunner, baseline_universe_path: Path, tmp_path: Path
    ):
        # Copy universe to temp dir where there's no astra.yaml
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
        # Run in a directory without astra.yaml
        result = runner.invoke(main, ["info"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "No astra.yaml found" in result.output


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
        # Copy analysis to temp dir
        temp_analysis = tmp_path / "astra.yaml"
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
        assert (tmp_path / "schemas" / "analysis.yaml").exists()
        assert (tmp_path / "schemas" / "universe.yaml").exists()

    def test_schema_show_analysis(self, runner: CliRunner):
        result = runner.invoke(main, ["schema", "show", "analysis"])
        assert result.exit_code == 0
        assert "Analysis" in result.output

    def test_schema_show_universe(self, runner: CliRunner):
        result = runner.invoke(main, ["schema", "show", "universe"])
        assert result.exit_code == 0
        assert "Universe" in result.output


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
        assert "ASTRA - Agentic Schema for Transparent Research Analysis CLI" in result.output

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
        """Test that basic init creates the minimal ASTRA scaffold."""
        project_dir = tmp_path / "my-analysis"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert "Created ASTRA analysis scaffold" in result.output

        # Check directory structure (minimal scaffold)
        assert (project_dir / "astra.yaml").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "universes").is_dir()
        assert (project_dir / "universes" / "baseline.yaml").exists()
        assert (project_dir / "src").is_dir()

        # Agentic scaffolding NOT created (init produces only the minimal spec scaffold)
        assert not (project_dir / ".claude").exists()
        assert not (project_dir / "CLAUDE.md").exists()
        assert not (project_dir / "workflows").exists()
        assert not (project_dir / "steps").exists()
        assert not (project_dir / "scripts").exists()

    def test_init_astra_yaml_content(self, runner: CliRunner, tmp_path: Path):
        """Test that the generated astra.yaml has the expected content."""
        project_dir = tmp_path / "content-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert (project_dir / "astra.yaml").exists()

        # Verify the file content
        content = (project_dir / "astra.yaml").read_text()
        assert "content-test" in content  # Directory name used as analysis name
        assert "version:" in content
        assert "decisions:" in content
        assert "recipe:" in content
        assert "container:" in content

    def test_init_gitignore_content(self, runner: CliRunner, tmp_path: Path):
        """Test gitignore content."""
        project_dir = tmp_path / "gitignore-test"
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0

        gitignore = (project_dir / ".gitignore").read_text()
        assert "__pycache__/" in gitignore
        assert ".venv/" in gitignore
        assert "outputs/" not in gitignore

    def test_init_existing_nonempty_dir_fails(self, runner: CliRunner, tmp_path: Path):
        """Test that init fails on existing non-empty directory."""
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        (project_dir / "some_file.txt").write_text("existing content")

        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 1
        assert "not empty" in result.output
        assert not (project_dir / "astra.yaml").exists()

    def test_init_refuses_if_astra_yaml_exists(self, runner: CliRunner, tmp_path: Path):
        """Test that init refuses to run in an existing ASTRA project."""
        project_dir = tmp_path / "already-init"
        # First init should succeed
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert (project_dir / "astra.yaml").exists()

        # Second init should fail
        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 1
        assert "already an ASTRA project" in result.output

    def test_init_refuses_if_astra_yaml_exists_current_dir(self, runner: CliRunner, tmp_path: Path):
        """Test that init refuses to run in current dir if astra.yaml exists."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # First init
            result = runner.invoke(main, ["init", "--no-git"])
            assert result.exit_code == 0

            # Second init should fail
            result = runner.invoke(main, ["init", "--no-git"])
            assert result.exit_code == 1
            assert "already an ASTRA project" in result.output
        finally:
            os.chdir(old_cwd)

    def test_init_existing_empty_dir_succeeds(self, runner: CliRunner, tmp_path: Path):
        """Test that init succeeds on existing empty directory."""
        project_dir = tmp_path / "existing-empty"
        project_dir.mkdir()

        result = runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert (project_dir / "astra.yaml").exists()

    def test_init_current_directory(self, runner: CliRunner, tmp_path: Path):
        """Test init with default '.' directory."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(
                main,
                ["init", "--no-git"],
            )
            assert result.exit_code == 0
            assert (tmp_path / "astra.yaml").exists()
        finally:
            os.chdir(old_cwd)

    def test_init_generated_files_are_valid(self, runner: CliRunner, tmp_path: Path):
        """Test that generated files pass validation."""
        project_dir = tmp_path / "valid-test"
        runner.invoke(
            main,
            ["init", str(project_dir), "--no-git"],
        )

        # Validate the generated astra.yaml
        result = runner.invoke(main, ["validate", str(project_dir / "astra.yaml")])
        assert result.exit_code == 0
        assert "Validation successful" in result.output

        # Validate the generated baseline.yaml
        result = runner.invoke(
            main,
            [
                "validate",
                str(project_dir / "universes" / "baseline.yaml"),
                "-a",
                str(project_dir / "astra.yaml"),
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


class TestBatchQuoteVerification:
    """Tests for the batch quote verification command (astra paper verify-quotes)."""

    def test_verify_quotes_no_input(self, runner: CliRunner):
        """Test error handling when no input is provided on stdin."""
        result = runner.invoke(
            main,
            ["paper", "verify-quotes", "10.1234/test"],
            input="",  # Empty input
        )
        assert result.exit_code == 2
        output = json.loads(result.output)
        assert "error" in output
        assert "No input" in output["error"]

    def test_verify_quotes_invalid_json(self, runner: CliRunner):
        """Test error handling for malformed JSON input."""
        result = runner.invoke(
            main,
            ["paper", "verify-quotes", "10.1234/test"],
            input="not valid json{",
        )
        assert result.exit_code == 2
        output = json.loads(result.output)
        assert "error" in output
        assert "Invalid JSON" in output["error"]

    def test_verify_quotes_paper_not_cached(self, runner: CliRunner):
        """Test error when paper is not in cache."""
        input_data = json.dumps({"quotes": [{"text": "some quote"}]})
        result = runner.invoke(
            main,
            ["paper", "verify-quotes", "10.9999/nonexistent"],
            input=input_data,
        )
        assert result.exit_code == 2
        output = json.loads(result.output)
        assert "error" in output
        assert "not in cache" in output["error"]

    def test_verify_quotes_empty_quotes_list(self, runner: CliRunner):
        """Test handling of empty quotes list."""
        input_data = json.dumps({"quotes": []})
        result = runner.invoke(
            main,
            ["paper", "verify-quotes", "10.9999/nonexistent"],
            input=input_data,
        )
        # Either error (not cached) or success with empty results
        assert result.exit_code in (0, 2)

    def test_verify_quotes_output_format(self, runner: CliRunner):
        """Test that output has the expected JSON structure."""
        input_data = json.dumps({"quotes": [{"text": "test quote"}]})
        result = runner.invoke(
            main,
            ["paper", "verify-quotes", "10.9999/test", "--version", "1"],
            input=input_data,
        )
        # Will fail because paper not cached, but check structure
        output = json.loads(result.output)
        assert "doi" in output
        assert output["doi"] == "10.9999/test"
        assert "version" in output
        assert output["version"] == 1
        # Either results or error
        assert "results" in output or "error" in output
        assert "summary" in output

    def test_verify_quotes_help(self, runner: CliRunner):
        """Test help output for verify-quotes command."""
        result = runner.invoke(main, ["paper", "verify-quotes", "--help"])
        assert result.exit_code == 0
        assert "Verify multiple quotes" in result.output
        assert "stdin" in result.output
        assert "JSON" in result.output
