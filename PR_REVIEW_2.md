# PR #2 Review: Workflow Integration (workflow branch)

**Reviewer:** Claude
**Date:** 2026-01-22
**Branch:** `workflow` -> `main`

## Summary

This PR adds CWL (Common Workflow Language) workflow integration to ASP, enabling automatic generation of workflow parameters from universe definitions and validation of ASP-to-CWL mappings.

**Stats:** +2,241 / -286 lines across 20 files

## New Components

### 1. Workflow Models (`src/asp/models/workflow.py`)
Well-structured Pydantic models for:
- `ParameterMapping`: Explicit ASP-to-CWL parameter mappings
- `WorkflowConfig`: Workflow configuration with path and mappings
- `CWLParameter`: Parsed CWL input parameter representation
- `WorkflowValidationError`: Dataclass for structured validation errors

### 2. CWL Parser (`src/asp/workflow/parser.py`)
Parses CWL v1.0/v1.1/v1.2 input definitions. Handles:
- List and dict input formats
- Optional types (`string?`, `["null", "string"]`)
- Complex types (arrays, records, enums)

### 3. Workflow Validator (`src/asp/workflow/validator.py`)
Two-level validation:
- **Syntax validation**: Uses `cwltool --validate`
- **Mapping validation**: Checks ASP decisions map to CWL parameters

### 4. Parameter Mapping (`src/asp/workflow/mapping.py`)
Convention-based automatic mapping:
- Simple values: `{decision_id}` -> value
- Dict values: `{decision_id}_{key}` -> value for each key
- File inputs: Resolved to CWL `File` objects

### 5. Parameter Generator (`src/asp/workflow/generator.py`)
Generates CWL parameter YAML files from ASP universes.

## CLI Changes (`src/asp/cli.py`)

New commands added:
- `asp params <universe>`: Generate CWL parameters from a universe
- `asp workflow validate --cwl <file>`: Validate CWL against ASP
- `asp workflow show --cwl <file>`: Show CWL inputs with ASP mappings
- `asp workflow run <universe> --cwl <file>`: Execute workflow via cwltool

Project structure updated:
- Removed `scripts/` directory in favor of CWL steps
- Added `.claude/skills/asp-analysis/` with skill template

## Test Coverage

Excellent test coverage with **31 new tests** for workflow functionality:
- `test_workflow_mapping.py`: 21 tests covering naming conventions, value extraction, input resolution
- `test_workflow_validation.py`: 10 tests covering CWL parsing and decision coverage validation

**All 164 tests pass.**

## Code Quality

- **Ruff:** All checks pass
- **MyPy:** Pre-existing stub issues (pydantic, PyYAML), not introduced by this PR
- Clean separation of concerns across modules
- Good docstrings and type annotations

## Recommendations

### Minor Issues to Consider

1. **`validator.py:26-31`** - The `subprocess.run` for `cwltool --validate` doesn't handle the case where `cwltool` is not installed. Consider catching `FileNotFoundError`:
   ```python
   try:
       result = subprocess.run(...)
   except FileNotFoundError:
       return [WorkflowValidationError("CWLTOOL_NOT_FOUND", "cwltool is not installed")]
   ```

2. **`cli.py:888-889`** - The `workflow run` command creates a temp file but could fail between creation and cleanup if an exception is raised during cwltool execution. The `finally` block handles this, but using a context manager would be cleaner:
   ```python
   with tempfile.NamedTemporaryFile(..., delete=True) as f:
       ...
   ```

3. **Missing CLI tests** - The new `workflow` CLI commands don't have dedicated tests in `test_cli.py`. Consider adding basic tests for:
   - `asp params` output format
   - `asp workflow show` table rendering

### Documentation

The SKILL.md template is comprehensive (636 lines). Consider whether all this content needs to be copied into each project or if it could reference the package documentation.

## Verdict

**Approve with minor suggestions.** This is a well-designed, well-tested addition that enables ASP to generate CWL workflow parameters automatically. The convention-based mapping approach is pragmatic and the validation tooling provides good feedback for users.
