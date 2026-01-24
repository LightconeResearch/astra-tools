.PHONY: schemas validate test lint typecheck check check-schemas install clean help

# Default target
help:
	@echo "ASP Development Commands"
	@echo ""
	@echo "  make schemas      - Generate JSON schemas from Pydantic models"
	@echo "  make validate     - Validate all example files"
	@echo "  make test         - Run test suite"
	@echo "  make lint         - Run linter (ruff)"
	@echo "  make typecheck    - Run type checker (mypy)"
	@echo "  make check-schemas- Check schemas are in sync with models"
	@echo "  make check        - Run all checks (lint, typecheck, test, validate, schema sync)"
	@echo "  make install      - Install package in development mode"
	@echo "  make clean        - Remove build artifacts"
	@echo ""

# Generate schemas from Pydantic models
schemas:
	@echo "Generating schemas..."
	@python tools/generate_schemas.py
	@echo ""
	@echo "Review changes and commit if correct:"
	@echo "  git diff spec/draft/"

# Validate all example files (uses JSON schema from spec/draft/)
validate:
	@echo "Validating examples/valid/..."
	@for f in $$(find examples/valid -name "asp.yaml" 2>/dev/null); do \
		echo "  ✓ $$f"; \
		asp validate "$$f" || exit 1; \
		dir=$$(dirname "$$f"); \
		if [ -d "$$dir/universes" ]; then \
			for u in "$$dir/universes"/*.yaml; do \
				if [ -f "$$u" ]; then \
					echo "    ✓ $$u"; \
					asp validate "$$u" -a "$$f" || exit 1; \
				fi; \
			done; \
		fi; \
	done
	@# Also validate standalone yaml files
	@for f in examples/valid/minimal.yaml examples/valid/full.yaml; do \
		if [ -f "$$f" ]; then \
			echo "  ✓ $$f"; \
			asp validate "$$f" || exit 1; \
		fi; \
	done
	@echo ""
	@echo "Checking examples/invalid/ properly fail..."
	@for f in examples/invalid/*.yaml; do \
		if [ -f "$$f" ]; then \
			if asp validate "$$f" 2>/dev/null; then \
				echo "  ✗ $$f should have failed but passed"; \
				exit 1; \
			else \
				echo "  ✓ $$f (correctly failed)"; \
			fi; \
		fi; \
	done
	@echo ""
	@echo "All examples validated successfully."

# Run tests
test:
	@pytest tests/ -v

# Run linter
lint:
	@ruff check asp/ models/ tests/
	@ruff format --check asp/ models/ tests/

# Run type checker
typecheck:
	@mypy asp/ models/

# Check schemas are in sync with models
check-schemas:
	@python tools/check_schema_changes.py

# Run all checks before commit
check: lint typecheck test validate check-schemas
	@echo ""
	@echo "All checks passed!"

# Install in development mode
install:
	@pip install -e ".[dev]"

# Clean build artifacts
clean:
	@rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts."
