# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

astra-tools is the validator, the checker and a runner's building blocks for ASTRA v0.1
analyses. It is being rebuilt for ASTRA 0.1 on the `v0.1` branch: it reads only `0.1.x` files.
Older files need astra-tools 0.2.18.

- **astra-spec** ([separate repo](https://github.com/LightconeResearch/astra-spec)) owns the
  specification. astra-tools installs it from `../astra-spec-pinned`, a worktree of
  `../astra-spec` pinned to one commit (see Development). At runtime astra-tools reads its
  data from the namespace package `astra.schema`: the JSON Schemas (`generated/*.schema.json`)
  and the rule catalogue (`generated/rules.json`: every code's layer, level and statement).
  Nothing is copied, so a change there costs astra-tools nothing. astra-spec ships no Python
  models.
- **astra-tools** (this repo) owns the tooling. It doesn't depend on, or prescribe, any
  agentic layer or UI; lightcone-cli and others consume its API and its `--json` output.

Both packages share the `astra` namespace (PEP 420). There is **no** `src/astra/__init__.py`.

## Design and plan

- `design/2026-11-04-v0.1-tooling-design.md`: the design (cited as *design §n*). Its
  specification is astra-spec `v0.1-schema` and its fix plan
  (`git -C ../astra-spec show da76cda:design/2026-11-04-v0.1-review-fixes.md`, *fix Xnn*).
- `design/2026-11-04-v0.1-phase-0-now-plan.md`: the implementation plan for phase 0's "now"
  items, with the decisions R1-R15 that refine the design.
- `design/2026-11-05-v0.1-phase-0-second-half-plan.md`: the plan for phase 0's second half
  (`load.py`, `contract.py`, `astra validate`, `schema`, `guide`, `spec`), with the decisions
  R16-R35 beside the "now" plan's.
- `design/2026-11-06-v0.1-phase-0-follow-up-plan.md`: phase 0's follow-up, at astra-spec
  `ebb143f` and then `b8f5597` (the parse layer, depth, and the review's bugs A1-A11), with the
  decisions R36-R50.
- Design commits land on `v0.1-design` and are merged into `v0.1`. The follow-up plan, and its
  edits to the two earlier plans, were committed on `v0.1` instead (R49).

## Layout and layers

Each layer may import only from the layers listed before it (design §3, with layer 1 in R12's
order). Phase 0 builds `diagnostics.py`, `sources/{paths,git,reader}.py`, `cache.py`,
`hashing.py`, `load.py`, `contract.py`, `validate.py`, `api.py`, `reference.py` and the `cli/`
commands; the rest comes in later phases (design §16).

```
src/astra/                no __init__.py: astra-spec owns astra.schema
  py.typed
  # 0. foundations: pure, no IO
  grammar.py              id, address, reference, option reference, condition: parse and format
  model.py                frozen dataclasses for the documents
  diagnostics.py          Location, Diagnostic, Rule, Catalogue (from rules.json), unchecked()
  # 1. reading: every byte comes through a Reader
  sources/paths.py        pure path checks; `..` removed as text
  sources/git.py          Repository, through the git binary
  sources/reader.py       the Reader protocol; WorktreeReader, CommitReader, MemoryReader
  cache.py                the cache directory and its get/put interface
  sources/remote.py       per-URL stores, fetching, materialize()
  sources/standins.py     the stand-in extension point and its built-ins
  load.py                 astra.yaml as strict YAML 1.2 with positions; records as strict JSON
  contract.py             JSON Schema validation and the error -> code mapping, and `check_file`,
                          which binding shares
  # 2. binding
  stack.py                bind(reader) -> Bound(stack | None, diagnostics)
  # 3. semantics: pure functions of a Stack
  universes.py            the universe being built, effective selections, activity, driving
  rules/                  validator checks, one module per topic
  validate.py             validate(): load, contract, bind, rules -> ValidationReport
  plan.py                 planned results and their dependency graph; render_command
  view.py                 the universe view
  # 4. results
  hashing.py              sha256 and size, through the cache
  records.py              record layout, reading, atomic writing, landing, runner helpers
  environments.py         the environment extension point
  check.py                statuses of records, bytes and evidence; the fingerprint
  history.py              record history and its queries (phase 4)
  # 5. surfaces
  api.py                  the stable public functions
  cli/                    one module per command, loaded lazily; rich only under cli/text/
  evidence/               papers by DOI, PDF text, quote checking (extra [evidence])
  reference.py            `astra spec`, through LinkML (extra [reference])
  scaffold.py             `astra init`
```

`examples/` still holds pre-0.1 analyses; phase 1 moves them to v0.1. CI (`.github/`) runs
only for `main` and is left alone on this branch.

## Global constraints

- Python `>= 3.11`. On 3.11, `Traversable.joinpath` takes one argument: write
  `files("astra.schema") / "generated" / "rules.json"`.
- Core dependencies are exactly `astra-spec`, `click`, `jsonschema`, `rich` and `ruamel.yaml`.
  - pydantic, PyYAML and httpx are not dependencies of the core, and nothing in astra-tools
    imports them.
  - The `[reference]` extra's linkml-runtime does bring pydantic and PyYAML into `uv.lock`
    and into `astra-tools[reference]`.
- git only through the `git` binary, by `subprocess`. Never libgit2, dulwich or GitPython.
- No module-level mutable state.
  - No module-level caches or consoles, no `functools.cache` or `lru_cache` on loaders, and
    nothing mutated after import.
  - Module constants are immutable (`tuple`, `frozenset`, `MappingProxyType`).
  - Click command objects are the one kind of module-level instance allowed: `astra.cli.main`,
    and the `command` each `CommandSpec` targets. They are built at import and never changed
    afterwards.
  - `astra.cli.main` swaps `sys.stdout` for a guard while it runs, and restores it (R30);
    `main` isn't re-entrant across threads.
- Every write is atomic: a temporary file in the same directory, then `os.replace`.
- The cache lives outside every repository: a relative `ASTRA_CACHE_DIR` is refused, and so is
  a cache inside the work tree being read. The defaults never give a relative path.
- `rich` is imported only under `src/astra/cli/text/`.
- Never create `src/astra/__init__.py` or `src/astra/schema/`: either would hide astra-spec's
  `astra.schema`.
- `uv run mypy --strict src/`, `uv run ruff check src/ tests/` and
  `uv run ruff format --check src/ tests/` pass. Ruff: line length 100, `py311`, rules
  `E F I N W UP`.
- Never modify `../astra-spec` or `../astra-spec-pinned` (move the pin only by checking out another commit there).
- Import cost is part of the API: `tests/test_import_cost.py` lists what importing each module
  may pull in. A new module is added there.
- Levels come from the catalogue: `MUST` is an error, `SHOULD` a warning. Codes outside it are
  advisory, prefixed `EVIDENCE_` or `PLAN_`, and always warnings.

## Development

astra-spec is an **editable** path source (`[tool.uv.sources]`, R3) pointing at
`../astra-spec-pinned`: a git worktree of `../astra-spec` detached at one commit, so the spec's
ongoing updates can't move under the tests. Never edit it. The pin is this commit, which
`git -C ../astra-spec-pinned rev-parse HEAD` must print:

    b8f55970258b0ee03ff6c10a0821427e2f8d3a0f

`uv.lock` records only the path, so this line is the record of which spec each astra-tools
commit was tested against. On a new machine, make the worktree once, then sync:

```bash
git -C ../astra-spec worktree add --detach ../astra-spec-pinned b8f55970258b0ee03ff6c10a0821427e2f8d3a0f
uv sync                                  # the venv, with the dev group and the [reference] extra
uv run pytest
uv run mypy --strict src/
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

To move the pin, check out another commit there and reinstall. Edit the hash above in the same
commit as the change that moves it:

```bash
git -C ../astra-spec-pinned checkout --detach <commit>
uv sync --reinstall-package astra-spec   # also refreshes the version and astra/docs/llms.txt
```

The pytest header prints the installed astra-spec version. A sync can rewrite `uv.lock`, which
is committed.

The dev group installs `astra-tools[reference]`, so linkml-runtime is in the venv: `astra spec`'s
tests run, and the import-cost tests' "no linkml_runtime" checks have something to miss (R33).

Two environment variables matter: `ASTRA_CACHE_DIR` moves the cache (it must be absolute; the
tests point it at a temporary directory of their own), and `ASTRA_DEBUG`, when non-empty, prints
an internal error's traceback.

Versioning comes from git tags (hatch-vcs). Commit subjects follow `Area: what changed`.
