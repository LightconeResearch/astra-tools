# ASTRA tools - Agentic Schema for Transparent Research Analysis

[![CI](https://github.com/LightconeResearch/ASTRA/actions/workflows/ci.yml/badge.svg)](https://github.com/LightconeResearch/ASTRA/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-green.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Python CLI and SDK for working with ASTRA analysis specifications.

> For an overview of ASTRA, the specification, concepts, and design rationale, see the main repository: **[astra-spec](https://github.com/LightconeResearch/astra-spec)**.

This repository provides the tooling layer: validation, CLI, paper management, and evidence verification.

## Install

Install the `astra` CLI globally from PyPI with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install astra-tools
```

`astra` is then available on your `PATH`.

For development, follow [CLAUDE.md](CLAUDE.md#development): this branch needs astra-spec checked out beside it, as a worktree pinned to one commit (`../astra-spec-pinned`), before `uv sync` can work. Then invoke commands through `uv run` (e.g. `uv run pytest`).

## On this branch

astra-tools is being rebuilt for ASTRA 0.1 on the `v0.1` branch; use astra-tools 0.2.18 for older files (`uv tool install astra-tools==0.2.18`). `astra init` isn't back yet. These commands work:

```bash
astra validate [PATH] [--json]   # check astra.yaml at the parse and schema layers; lists the validator rules not checked yet
astra rules                       # the rules of the ASTRA specification, by layer
astra rules MISSING_DECISION      # one rule in full
astra schema show NAME            # a JSON Schema of astra-spec's, verbatim: analysis, provenance, provenance.open
astra schema export DIR           # write the three as DIR/NAME.schema.json
astra guide                       # astra-spec's llms.txt for agents, verbatim; still being written for 0.1
astra spec [TERM]                 # the fields of ASTRA files, or one class, enum, type or field (Class.field)
eval "$(astra completion bash)"   # tab completion; zsh and fish too
```

`astra spec` reads astra-spec's LinkML sources through linkml-runtime, an optional extra: install it with `uv tool install 'astra-tools[reference]'`.

astra-spec's own [examples](https://github.com/LightconeResearch/astra-spec/tree/main/examples) are the reference analyses.

## Links

- [astra-spec](https://github.com/LightconeResearch/astra-spec) – specification, schemas, and primary documentation

## License

BSD 3-Clause
