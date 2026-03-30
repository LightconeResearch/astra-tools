#!/usr/bin/env python3
"""Generate artifacts from the LinkML ASTRA schema.

Requires: pip install linkml (dev dependency only)

Generates:
  - JSON Schema (for YAML validation)
  - JSON-LD context (for RO-Crate export)
  - Pydantic models (for Python SDK)
"""

import subprocess
import sys
from pathlib import Path

SCHEMA = Path("src/astra/schema/astra.yaml")
GENERATED = Path("src/astra/schema/generated")


def run(cmd: list[str], output: Path) -> None:
    """Run a generator command and write output to file."""
    print(f"  {' '.join(cmd)} > {output}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    output.write_text(result.stdout)


def main() -> None:
    if not SCHEMA.exists():
        print(f"Schema not found: {SCHEMA}", file=sys.stderr)
        sys.exit(1)

    GENERATED.mkdir(parents=True, exist_ok=True)

    schema = str(SCHEMA)

    print("Generating artifacts from LinkML schema...")
    run(["gen-json-schema", schema], GENERATED / "astra.schema.json")
    run(["gen-jsonld-context", schema], GENERATED / "astra_context.jsonld")
    run(["gen-pydantic", schema], GENERATED / "astra_models.py")

    print(f"\nGenerated 3 artifacts in {GENERATED}/")


if __name__ == "__main__":
    main()
