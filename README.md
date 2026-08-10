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

`astra` is then available on your `PATH`. For development (editable install with test/lint deps), clone the repo and run `uv sync --extra dev`, then invoke commands via `uv run` (e.g. `uv run pytest`).

## Quick Start

```bash
astra init my-analysis
cd my-analysis
astra validate            # validates every spec and universe file in the project
```

See [examples/iris/](examples/iris/) for a complete working example.

## CLI

Run `astra --help` for the full command list. Key commands:

- `astra init` – scaffold a new analysis project
- `astra validate` – validate the whole project, or one spec/universe file (add `--verify-evidence` to check quotes)
- `astra info` / `astra viz` – inspect the analysis and decision space
- `astra universe generate|check` – manage universes
- `astra spec` – render the schema as agent-friendly reference text
- `astra guide` – print the agent briefing (llms.txt) shipped with astra-spec
- `astra schema export|show` – work with JSON schemas
- `astra paper ...` – download, cache, and verify quotes against papers

`astra validate` and `astra info` accept `--json` to emit their report as a single JSON-encoded string (exit codes unchanged), convenient for embedding in agent tool output.

## Links

- [astra-spec](https://github.com/LightconeResearch/astra-spec) – specification, schemas, and primary documentation

## License

BSD 3-Clause
