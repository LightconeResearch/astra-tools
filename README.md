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

[Installation](https://astra-spec.org/0.1.0rc1/installation/)
gives the details.

## First use

```console
$ astra init my-analysis
✓ created astra.yaml
✓ created .gitignore
✓ created .git
✓ Converged ASTRA analysis scaffold: my-analysis
$ astra validate my-analysis
astra.yaml: valid, 0 error(s), 0 warning(s)
```

`astra init` writes an empty `astra.yaml`, with a `spec_version` and a label, in a git
repository; run again, it changes nothing. Once the analysis has outputs, `astra plan` shows
where each result's record and bytes go, and the command that builds it.
[Getting started](https://astra-spec.org/0.1/getting-started/) goes further.

## Commands

| Command | What it does |
|---|---|
| [`astra init`](https://astra-spec.org/0.1.0rc1/cli/#astra-init) | Make a minimal analysis, or complete one (idempotent) |
| [`astra validate`](https://astra-spec.org/0.1.0rc1/cli/#astra-validate) | Validate an analysis and its whole stack, or every analysis under the current folder |
| [`astra info`](https://astra-spec.org/0.1.0rc1/cli/#astra-info) | Show an analysis in brief |
| [`astra universe`](https://astra-spec.org/0.1.0rc1/cli/#astra-universe) | List the universes, or show one's selection |
| [`astra plan`](https://astra-spec.org/0.1.0rc1/cli/#astra-plan) | Show the planned results, their places and commands |
| [`astra check`](https://astra-spec.org/0.1.0rc1/cli/#astra-check) | Check the records and bytes of the planned results |
| [`astra spec`](https://astra-spec.org/0.1.0rc1/cli/#astra-spec) | Describe the fields of ASTRA files |
| [`astra schema`](https://astra-spec.org/0.1.0rc1/cli/#astra-schema) | Show or export the LinkML schemas |
| [`astra guide`](https://astra-spec.org/0.1.0rc1/cli/#astra-guide) | Print the guide for agents |
| [`astra paper`](https://astra-spec.org/0.1.0rc1/cli/#astra-paper) | Keep papers by DOI, and verify quotes in them |

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
