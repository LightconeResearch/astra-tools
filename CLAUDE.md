# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

astra-tools is the validator, the checker and a runner's building blocks for ASTRA v0.1
analyses. It reads only `0.1.x` files; older files need its 0.2 line (`astra-tools<0.3`).

- **astra-spec** ([separate repo](https://github.com/LightconeResearch/astra-spec)) owns the
  specification. astra-tools installs it from `../astra-spec-pinned`, a worktree of
  `../astra-spec` pinned to one commit (see Development). At runtime astra-tools reads its
  data from the namespace package `astra.schema`: the JSON Schemas (`generated/*.schema.json`)
  and the rule catalogue (`generated/rules.json`: every code's layer, level and statement).
  Nothing is copied. astra-spec ships no Python models.
- **astra-tools** (this repo) owns the tooling. It doesn't depend on, or prescribe, any
  agentic layer or UI; lightcone-cli and others consume `astra.api` and the `--json` shapes.

Both packages share the `astra` namespace (PEP 420). There is **no** `src/astra/__init__.py`.

## Design

- `design/2026-11-07-v0.1-tooling-design.md` is the design (cite it as *design §n*). A *§n* or
  *Annex X* in code, tests and the design refers to the long version of astra-spec's
  `docs/specification.md`, at astra-spec's tag `v0.1-long-spec`. The specification at the
  pinned commit is the short one, whose sections are Elements, Results, Rules and Schema
  files. Design §1's
  principles bind every change; §5's table holds the open questions, each
  marked `# OPEN(<id>)` in the one place that keeps its reading; §6 gives each phase's brief.
- Cite the design and the spec in code and docstrings, never decision numbers.
- A question about the spec's meaning that neither the spec nor the design answers: take the
  simplest reading, add a row to §5's table, and mark the code `# OPEN(<id>)`. A choice that is
  astra-tools' own (an output shape, a command's behaviour, an exit code) is no open question:
  make it by §1's principles, and write it into the design where a user would need to know it.

## Layout and layers

A pipeline: read → load → contract → bind → {rules, plan, view, check}. Each layer imports only
from the layers before it (design §2).

```
src/astra/                no __init__.py: astra-spec owns astra.schema
  py.typed
  # 0. foundations: pure, no IO
  diagnostics.py          Location, Diagnostic, the Catalogue read from rules.json
  grammar.py              the forms of a name (Annex C)
  model.py                frozen dataclasses for the two documents
  # 1. reading: every byte comes through a Reader
  sources/paths.py        paths tidied as text (Annex B)
  sources/git.py          Repository: the git binary, and nothing else
  sources/reader.py       the Reader protocol; WorktreeReader, CommitReader
  sources/remote.py       per-URL stores of remote repositories, in the cache
  sources/standins.py     the stand-ins astra-tools recognises (entry points astra.standins)
  cache.py                one directory of plain files, get and put; its namespaces are
                          remotes, validity, hashes, worktrees and papers
  load.py                 astra.yaml and records, as Annex A reads them
  contract.py             the schema layer: JSON Schema and the error map (Annex D)
  # 2. binding
  stack.py                bind(reader, root) -> Bound(stack | None, diagnostics)
  # 3. meaning: pure functions of a Stack
  universes.py            what each universe selects, what each switch takes, what is built,
                          reached, planned and used, what is driven, pins and imports, the
                          universes built, planned results, their names and places
  rules/                  the validator rules, one module per section of Part II
  validate.py             validate() -> ValidationReport
  plan.py                 plan() -> Plan, and render_command
  view.py                 view() -> UniverseView
  # 4. results
  hashing.py              SHA-256 and size, through the cache
  records.py              reading and writing records; the runner's helpers
  environments.py         the environment extension point (entry points astra.environments)
  check.py                check() -> CheckReport
  history.py              records over time, read from git on demand
  # 5. surfaces
  api.py                  the stable public functions
  cli/                    one module per command, loaded lazily; rich only in cli/text/
  reference.py            `astra spec`, through LinkML (extra [reference])
  evidence/               papers by DOI and quotes sought in them (extra [evidence])
docs/
  cli.md                  the CLI reference, shown on astra-spec.org at /cli/
  installation.md         installing astra-tools, shown on astra-spec.org at /installation/
```

## Global constraints

- Python `>= 3.11`. On 3.11, `Traversable.joinpath` takes one argument: write
  `files("astra.schema") / "generated" / "rules.json"`.
- Core dependencies are exactly `astra-spec`, `click`, `jsonschema`, `rich` and `ruamel.yaml`.
  pydantic, PyYAML and httpx are not dependencies of the core, and nothing in astra-tools
  imports them (the `[reference]` extra's linkml-runtime brings them into `uv.lock`).
  The extras are `[reference]` (linkml-runtime) and `[evidence]` (pypdf, rapidfuzz); the dev
  group installs both, and `astra --help`, completion and `validate --json` import neither.
- git only through the `git` binary, by `subprocess`. Never libgit2, dulwich or GitPython.
- No module-level mutable state: no module-level caches or consoles, no `functools.cache` on
  loaders, nothing mutated after import; module constants are immutable (`tuple`,
  `frozenset`, `MappingProxyType`). Click command objects are the one kind of module-level
  instance allowed.
- Every write is atomic: a temporary file in the same directory, then `os.replace`.
- The cache lives outside every repository: a relative `ASTRA_CACHE_DIR` is refused.
- `rich` is imported only under `src/astra/cli/text/`.
- Never create `src/astra/__init__.py` or `src/astra/schema/`: either would hide astra-spec's
  `astra.schema`.
- Import cost is part of the API: `tests/test_import_cost.py` lists what importing each module
  may pull in. A new module is added there.
- Levels come from the catalogue: `MUST` is an error, `SHOULD` a warning. The only codes
  outside it are astra-tools' own three, in `diagnostics.py` (`UNSUPPORTED_SPEC_VERSION` and
  `REMOTE_UNREACHABLE`, errors; `COMMIT_NOT_ANCESTOR`, a warning; design §3), and the
  `[evidence]` extra's advisory `EVIDENCE_` warnings, which never change a verdict, a status or
  an exit code. When a rule isn't checked is astra-tools' own policy, design §4.13.
- Never modify `../astra-spec` or `../astra-spec-pinned` (move the pin only by checking out
  another commit there).
- `docs/cli.md` and `docs/installation.md` are the pages astra-spec.org shows for astra-tools:
  its docs build copies them from this repository. A change to a command, an option or an extra
  changes them in the same commit. `tests/test_cli_docs.py` checks that every command,
  subcommand and option has its place in `docs/cli.md`. Their links into the specification are
  full URLs, `https://astra-spec.org/0.1/...`, so that they work here too.
- `README.md` is also the PyPI page, fixed at each upload. Its links are full URLs, since
  relative ones break on PyPI.

## Development

astra-spec is an **editable** path source (`[tool.uv.sources]`) pointing at
`../astra-spec-pinned`: a git worktree of `../astra-spec` detached at one commit, the pin.
`astra-spec.pin`, at the top of this repository, holds the pin's full commit id on one line, and
`git -C ../astra-spec-pinned rev-parse HEAD` must print the same. `uv.lock` records only the
path, so `astra-spec.pin` is the record of which spec each astra-tools commit was tested
against. CI and the release workflow check astra-spec out at that commit, so it must be on
GitHub. On a new machine:

```bash
git -C ../astra-spec worktree add --detach ../astra-spec-pinned "$(cat astra-spec.pin)"
uv sync                                  # the venv, with the dev group and both extras
uv run --frozen pytest -q -p no:cacheprovider
uv run --frozen mypy --strict src/
uv run --frozen ruff check src/ tests/
uv run --frozen ruff format --check src/ tests/
```

To move the pin, write another commit's full id into `astra-spec.pin`, in the same commit as the
changes that follow it, then check that commit out there and reinstall:

```bash
git -C ../astra-spec-pinned checkout --detach "$(cat astra-spec.pin)"
uv sync --reinstall-package astra-spec
```

A release pins the commit of an astra-spec tag that its dependency on astra-spec accepts
(`v0.1.0rc1` for `astra-spec==0.1.0rc1`). The release workflow fails otherwise, and publishes
nothing.

Two environment variables matter: `ASTRA_CACHE_DIR` moves the cache (it must be absolute; the
tests point it at a temporary directory of their own), and `ASTRA_DEBUG`, when non-empty, prints
an internal error's traceback.

Versioning comes from git tags (hatch-vcs). Commit subjects follow `Area: what changed`.
