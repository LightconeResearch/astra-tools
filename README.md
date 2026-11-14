# astra-tools

[![CI](https://github.com/astra-project/astra-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/astra-project/astra-tools/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-green.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

astra-tools is the reference tooling for [ASTRA 0.1](https://astra-spec.org/0.1/), the Agentic
Schema for Transparent Research Analysis. Its command, `astra`, validates an analysis and every
analysis it declares, shows what it plans to build and how it looks in each universe, checks what
was built against its records, and reads those records' history from git. It runs no recipe: a
runner builds the results and records them, through astra-tools' Python API or its `--json`
output.

astra-tools reads ASTRA 0.1 files. ASTRA 0.0.x files need its 0.2 line.

## Install

```bash
uv tool install astra-tools
```

Or `pip install astra-tools`. It needs Python 3.11 or later, and git.

While astra-tools for ASTRA 0.1 has only release candidates, uv and pip skip them. Ask for them
with `uv tool install --prerelease allow astra-tools`, or `pip install --pre astra-tools`.

For ASTRA 0.0.x files, install the 0.2 line:

```bash
uv tool install 'astra-tools<0.3'
```

`astra spec` needs the `[reference]` extra, and `astra paper` the `[evidence]` extra.
[Installation](https://astra-spec.org/0.1.0rc1/installation/)
gives the details.

## First use

```console
$ astra init my-analysis
Made my-analysis/astra.yaml, in a new git repository.
Check it with: astra validate my-analysis
$ astra validate my-analysis
astra.yaml: valid, 0 error(s), 0 warning(s)
$ astra plan my-analysis
result
  record    .astra/records/result.json
  bytes     results/result.json
  run in    .
  command   python src/result.py 'results/result.json'
1 planned result(s)
```

`astra init` writes an `astra.yaml` with one output, `result`. `astra plan` shows where its
record and its bytes go, and the command that builds it.
[Getting started](https://astra-spec.org/0.1/getting-started/) goes further.

## Commands

| Command | What it does |
|---|---|
| [`astra init`](https://astra-spec.org/0.1.0rc1/cli/#astra-init) | Make a minimal analysis |
| [`astra validate`](https://astra-spec.org/0.1.0rc1/cli/#astra-validate) | Validate an analysis and its whole stack |
| [`astra info`](https://astra-spec.org/0.1.0rc1/cli/#astra-info) | Show the stack in brief |
| [`astra universe`](https://astra-spec.org/0.1.0rc1/cli/#astra-universe) | List the universes, or show one's selection |
| [`astra plan`](https://astra-spec.org/0.1.0rc1/cli/#astra-plan) | Show the planned results, their places and commands |
| [`astra view`](https://astra-spec.org/0.1.0rc1/cli/#astra-view) | Show the analysis as it is in one universe |
| [`astra check`](https://astra-spec.org/0.1.0rc1/cli/#astra-check) | Check the records and bytes of the planned results |
| [`astra history`](https://astra-spec.org/0.1.0rc1/cli/#astra-history) | Show what git holds of a result's records over time |
| [`astra rules`](https://astra-spec.org/0.1.0rc1/cli/#astra-rules) | List the rules, or show one |
| [`astra spec`](https://astra-spec.org/0.1.0rc1/cli/#astra-spec) | Describe the fields of ASTRA files |
| [`astra schema`](https://astra-spec.org/0.1.0rc1/cli/#astra-schema) | Show or export the JSON Schemas |
| [`astra guide`](https://astra-spec.org/0.1.0rc1/cli/#astra-guide) | Print the guide for agents |
| [`astra paper`](https://astra-spec.org/0.1.0rc1/cli/#astra-paper) | Keep cited papers, and seek quotes in them |
| [`astra cache`](https://astra-spec.org/0.1.0rc1/cli/#astra-cache) | Show or clear the cache |
| [`astra completion`](https://astra-spec.org/0.1.0rc1/cli/#astra-completion) | Print a shell completion script |

The [CLI reference](https://astra-spec.org/0.1.0rc1/cli/) gives
each command's options, exit codes and examples. The
[specification](https://astra-spec.org/0.1/) says what an analysis means and what each rule asks.

## Development

astra-tools is tested against the astra-spec release `uv.lock` installs from PyPI. The tests'
first run downloads that release's conformance suite, examples and test documents from its tag on
GitHub, and keeps them in `~/.cache/astra-tools-tests/`.

```bash
uv sync --frozen
```

The checks:

```bash
uv run --frozen pytest -q -p no:cacheprovider
uv run --frozen mypy --strict src/
uv run --frozen ruff check src/ tests/
uv run --frozen ruff format --check src/ tests/
```

[CLAUDE.md](https://github.com/astra-project/astra-tools/blob/main/CLAUDE.md) gives the
layout, the constraints the code keeps, and how to move to a new astra-spec release.

## Licence

BSD 3-Clause: see [LICENSE](https://github.com/astra-project/astra-tools/blob/main/LICENSE).
