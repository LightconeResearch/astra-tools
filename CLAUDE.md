# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

astra-tools is the **Python CLI and library** for ASTRA 0.1 analyses: validator, planner, checker and a runner's building blocks. It reads only `0.1.x` analyses; older ones need `astra-tools<0.3`.

**Architecture**:
- **astra-spec** ([separate repo](https://github.com/LightconeResearch/astra-spec)) = the specification. astra-tools reads its JSON Schemas and rule catalogue (`astra.schema`: `jsonschema/`, `rules/rules.json`) at run time, copying nothing.
- **astra-tools** (this repo) = tooling layer: validation, planning, checking, records, CLI, papers.

astra-tools is intentionally agnostic to any agentic layer or UI. It answers to the specification: argue from it, its conformance suite and its examples, never from one analysis that uses ASTRA.

Both `astra-spec` and this package share the `astra` Python namespace via implicit namespace packages (PEP 420). There is **no** `src/astra/__init__.py`, and never create `src/astra/schema/`.

## Repository Structure

```
src/astra/          # NO __init__.py (namespace package), in layers:
  0 foundations     diagnostics, grammar, model
  1 reading         sources/ (every byte read), cache, load, contract
  2 binding         stack
  3 meaning         universes, rules/, validate, plan, view
  4 results         hashing, records, environments, check, history
  5 surfaces        api (the stable functions), cli/, reference, evidence/
docs/               # cli.md and installation.md, shown on astra-spec.org
```

## Key Design Principles

1. **Layers**: a module imports only from its own layer or the ones before it. Rich is imported only under `cli/text/`.
2. **Levels come from the catalogue**: `MUST` is an error, `SHOULD` a warning. astra-tools' own codes are in `diagnostics.py`.
3. **Import cost is part of the API**: `tests/test_import_cost.py` lists what each module may import. Add new modules there.

## Development Commands

### Setup
astra-spec is installed, editable, from `../astra-spec-pinned`, a worktree at the commit in `astra-spec.pin`:
```bash
git -C ../astra-spec worktree add --detach ../astra-spec-pinned "$(cat astra-spec.pin)"
uv sync --frozen
```

### Testing and linting
```bash
uv run --frozen pytest -q -p no:cacheprovider
uv run --frozen mypy --strict src/
uv run --frozen ruff check src/ tests/
uv run --frozen ruff format --check src/ tests/
```

## Common Development Tasks

### Moving the pin
Write the new commit's full id into `astra-spec.pin`, in the same commit as the changes it needs, then:
```bash
git -C ../astra-spec-pinned checkout --detach "$(cat astra-spec.pin)"
uv sync --reinstall-package astra-spec
```
CI checks astra-spec out at the pin, so it must be a commit on astra-spec's main or a tag.

### Changing a command
Change `docs/cli.md` (and `docs/installation.md` for an extra) in the same commit; `tests/test_cli_docs.py` checks it. astra-spec.org shows both pages, so their links into the specification are full URLs.

## Configuration

- Python >=3.11 (on 3.11, `Traversable.joinpath` takes one argument)
- Ruff (line-length 100), mypy strict
- Versioning: hatch-vcs (from git tags)
- Core dependencies: astra-spec, click, jsonschema, rich, ruamel.yaml; extras `[reference]`, `[evidence]`

## Key Conventions

1. git only through the `git` binary; no module-level mutable state; every write atomic (`os.replace`).
2. `README.md` is the PyPI page, so its links are full URLs.
3. Commit subjects: `Area: what changed`.
