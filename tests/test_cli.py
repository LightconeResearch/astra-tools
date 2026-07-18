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


class TestSpecCommand:
    """Tests for the `spec` schema-reference renderer.

    Output is a pure transformation of the installed astra-spec schema, so
    these assert structural invariants and a few load-bearing concepts rather
    than exact prose.
    """

    def test_summary_groups_by_schema(self, runner: CliRunner):
        result = runner.invoke(main, ["spec"])
        assert result.exit_code == 0
        out = result.output
        assert "concept vocabulary" in out
        # The three schema layers appear as group headers, in display order.
        for label in ("ANALYSIS", "UNIVERSE", "INSIGHT"):
            assert label in out
        assert out.index("ANALYSIS") < out.index("UNIVERSE") < out.index("INSIGHT")

    def test_summary_footer_points_at_term_and_full(self, runner: CliRunner):
        result = runner.invoke(main, ["spec"])
        assert result.exit_code == 0
        assert "astra spec <term>" in result.output
        assert "astra spec --full" in result.output

    def test_summary_lists_core_concepts(self, runner: CliRunner):
        result = runner.invoke(main, ["spec"])
        for term in ("Analysis", "Decision", "Universe", "Insight"):
            assert term in result.output

    def test_term_renders_class_in_full(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "analysis"])
        assert result.exit_code == 0
        out = result.output
        assert out.startswith("# Analysis")
        assert "Fields:" in out
        # Slot ranges that are classes render as `astra spec <term>` links.
        assert "-> astra spec input" in out

    def test_term_lookup_is_case_insensitive(self, runner: CliRunner):
        lower = runner.invoke(main, ["spec", "analysis"])
        upper = runner.invoke(main, ["spec", "ANALYSIS"])
        assert lower.exit_code == upper.exit_code == 0
        assert lower.output == upper.output
        assert upper.output.startswith("# Analysis")

    def test_term_collapses_parallel_forbid_rules(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "decision"])
        assert result.exit_code == 0
        out = result.output
        assert "Rules:" in out
        # Rules sharing a title stem collapse to one line listing the suffixes.
        forbid_lines = [ln for ln in out.splitlines() if "From alias forbids:" in ln]
        assert len(forbid_lines) == 1
        assert forbid_lines[0].count(",") >= 1

    def test_enum_renders_values_and_used_by(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "inputtype"])
        assert result.exit_code == 0
        out = result.output
        assert "(enum)" in out
        assert "Values:" in out
        assert "data" in out
        assert "Used by:" in out

    def test_unknown_term_exits_1_and_lists_terms(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "not_a_real_term"])
        assert result.exit_code == 1
        assert "Unknown term" in result.output
        assert "Valid terms" in result.output
        # A genuine term is offered among the valid ones.
        assert "Analysis" in result.output

    def test_full_concatenates_every_entry(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "--full"])
        assert result.exit_code == 0
        out = result.output
        # Sanity: substantial, spanning far more than any single entry.
        assert len(out.splitlines()) > 300
        for heading in ("# Analysis", "# Decision", "# Universe"):
            assert heading in out
        # Enums are inlined into the fields that use them, not standalone entries.
        assert "# InputType" not in out
        assert "data | analysis" in out

    def test_cross_references_link_related_terms(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "decision"])
        out = result.output
        assert "References:" in out
        assert "Option (astra spec option)" in out
        assert "Used by:" in out
        assert "Analysis (astra spec analysis)" in out

    def test_self_recursive_edge_is_marked_not_dropped(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "analysis"])
        out = result.output
        # Analysis contains sub-Analyses; the self edge is flagged, not silent.
        assert "Analysis (self-recursive)" in out
        assert "Used by:" in out

    def test_term_collapses_forbid_rules_with_underscored_slots(self, runner: CliRunner):
        # Input's forbidden slots include multi-token names (ref_version,
        # use_outputs). All from_alias_forbids_* rules must collapse to ONE
        # line, with the underscored names intact as suffixes -- not orphaned
        # onto standalone "From alias forbids ref version" lines.
        result = runner.invoke(main, ["spec", "input"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        forbid_lines = [ln for ln in lines if "From alias forbids:" in ln]
        assert len(forbid_lines) == 1
        collapsed = forbid_lines[0]
        for slot in ("type", "label", "description", "source", "ref", "ref_version", "use_outputs"):
            assert slot in collapsed
        # No forbid slot fragments onto its own humanized rule line.
        assert not any("From alias forbids ref version" in ln for ln in lines)
        assert not any("From alias forbids use outputs" in ln for ln in lines)

    def test_class_description_rendered_verbatim(self, runner: CliRunner):
        # A class description renders VERBATIM with newlines preserved -- in
        # deliberate contrast to first-sentence-flattened field descriptions.
        # Decision carries an indented reference-grammar block that only
        # survives if the line breaks are kept.
        result = runner.invoke(main, ["spec", "decision"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        assert "Reference grammar:" in lines  # its own line, not folded in
        grammar_idx = lines.index("Reference grammar:")
        # The indented example lines follow on their own separate lines.
        block = lines[grammar_idx : grammar_idx + 4]
        assert any(ln.startswith("  from: ../id") for ln in block)
        assert any(ln.startswith("  from: ../../id") for ln in block)

    def test_field_table_derives_flags_and_pattern(self, runner: CliRunner):
        # Requiredness, multivalued/inlined flags, and pattern are induced from
        # the slots. Decision exercises all three.
        result = runner.invoke(main, ["spec", "decision"])
        out = result.output
        lines = out.splitlines()

        def field_line(name: str) -> str:
            return next(ln for ln in lines if ln.strip().startswith(name + " "))

        # `options` is a multivalued, inlined map of Option.
        opts = field_line("options")
        assert "multivalued" in opts and "inlined" in opts
        # `when` is multivalued but not inlined.
        when = field_line("when")
        assert "multivalued" in when and "inlined" not in when
        # `from` carries a pattern, emitted on its own indented line.
        assert any(ln.strip().startswith("pattern: ^(\\.\\./)") for ln in lines)

    def test_field_table_honors_slot_usage_overrides(self, runner: CliRunner):
        # Input.from and Output.from are the same slot with per-class
        # slot_usage overrides; they must render distinct patterns. This holds
        # only because the renderer reads class_induced_slots, not plain slots.
        input_from = runner.invoke(main, ["spec", "input"]).output
        output_from = runner.invoke(main, ["spec", "output"]).output
        input_pattern = r"^(\.\./)+[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
        output_pattern = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
        assert input_pattern in input_from
        assert output_pattern in output_from
        # The override is real: neither class shows the other's pattern.
        assert input_pattern not in output_from
        assert output_pattern not in input_from

    def test_field_table_renders_requiredness(self, runner: CliRunner):
        # Requiredness is a contract-named field-table property. Option pins both
        # tokens in one class: `label` is explicitly required and `id` is required
        # by LinkML identifier semantics, while the rest are optional. Inverting the
        # ternary (required<->optional) must fail this.
        result = runner.invoke(main, ["spec", "option"])
        assert result.exit_code == 0
        lines = result.output.splitlines()

        def field_line(name: str) -> str:
            return next(ln for ln in lines if ln.strip().startswith(name + " "))

        # `id` is `identifier: true`; class_induced_slots resolves it to required.
        for required_field in ("label", "id"):
            ln = field_line(required_field)
            assert "required" in ln and "optional" not in ln
        for optional_field in ("description", "excluded"):
            ln = field_line(optional_field)
            assert "optional" in ln and "required" not in ln

    def test_field_table_flattens_field_descriptions_to_first_sentence(self, runner: CliRunner):
        # First-sentence flattening is an accepted judgment call and load-bearing:
        # Recipe.command carries a multi-paragraph template description that would
        # dump into the table verbatim if `_first_sentence` were dropped. Only the
        # opening sentence survives; the later-paragraph body does not.
        result = runner.invoke(main, ["spec", "recipe"])
        assert result.exit_code == 0
        out = result.output
        assert "POSIX shell command to execute" in out
        # Tokens exclusive to later paragraphs of the command description; their
        # presence would mean the field description was rendered verbatim.
        assert "{inputs.<id>}" not in out
        assert "placeholders" not in out
        assert "Runners substitute" not in out

    def test_full_includes_every_schema_group(self, runner: CliRunner):
        # --full completeness is the whole point of the command. Pin at least one
        # heading from each of the three schema buckets so a regression dropping a
        # whole group (e.g. the insight per-schema loop) is caught, not just the
        # already-guarded analysis/universe ones.
        result = runner.invoke(main, ["spec", "--full"])
        assert result.exit_code == 0
        out = result.output
        for heading in (
            "# Analysis",  # analysis group
            "# Universe",  # universe group
            "# Evidence",  # insight group
            "# Insight",
            "# InsightCollection",
            "# TextQuoteSelector",
        ):
            assert heading in out, f"{heading} missing from --full"

    def test_full_with_term_is_rejected(self, runner: CliRunner):
        # --full and a positional TERM are mutually exclusive; passing both
        # errors rather than silently dumping the whole reference.
        result = runner.invoke(main, ["spec", "analysis", "--full"])
        assert result.exit_code != 0
        assert "--full" in result.output

    def test_spec_help(self, runner: CliRunner):
        result = runner.invoke(main, ["spec", "--help"])
        assert result.exit_code == 0
        assert "reference" in result.output.lower()
