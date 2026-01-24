# Contributing to ASP

Thank you for your interest in contributing to the Agentic Science Protocol!

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/ASP.git
   cd ASP
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

## Development Workflow

### Running Tests
```bash
make test          # Run all tests
make validate      # Validate example files
make check         # Run all checks (lint, typecheck, test, validate)
```

### Code Style
```bash
make lint          # Run ruff linter
ruff format .      # Auto-format code
```

### Schema Changes

The JSON schemas in `spec/draft/` are the versioned contract. If you modify Pydantic models:

1. Make your changes to `models/*.py`
2. Regenerate schemas: `make schemas`
3. Review the schema diff: `git diff spec/draft/`
4. Commit both model and schema changes together

**Important**: Schema changes should be intentional and reviewed. The CI will fail if schemas are out of sync with models.

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run `make check` to ensure all tests pass
4. Submit a pull request with a clear description

### PR Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation as needed
- Follow existing code style

## Project Structure

```
ASP/
├── spec/          # JSON Schema specification (the contract)
├── models/        # Pydantic models (generates spec/)
├── asp/           # Python SDK/CLI tooling
├── examples/      # Conformance test suite
├── tools/         # Build scripts
└── tests/         # Unit tests
```

## Design Proposals

For significant changes, consider writing an RFC in `rfcs/`:

1. Copy `rfcs/000-template.md` to `rfcs/NNN-your-proposal.md`
2. Fill in the template
3. Submit as a PR for discussion

## Questions?

Open an issue or start a discussion on GitHub.
