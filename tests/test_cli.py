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
