#!/usr/bin/env python3
"""Generate JSON schemas from Pydantic models.

This script regenerates the JSON schemas in spec/draft/ from the Pydantic models.
Run this after modifying any model in models/.

Usage:
    python tools/generate_schemas.py
    # or
    make schemas

Note: This tool imports directly from models/, NOT from asp/.
The asp package should never interact with Pydantic models.
"""

import json
from pathlib import Path
import sys

# Add project root to path so we can import models/
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.analysis import Analysis
from models.universe import Universe
from models.insight import InsightCollection


def generate_schema(model_class, output_path: Path) -> None:
    """Generate JSON schema from a Pydantic model."""
    schema = model_class.model_json_schema(mode="serialization")
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")


def main():
    output_dir = project_root / "spec" / "draft"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating schemas to {output_dir}...")

    # Generate each schema
    schemas = [
        (Analysis, "analysis.schema.json"),
        (Universe, "universe.schema.json"),
        (InsightCollection, "insights.schema.json"),
    ]

    for model_class, filename in schemas:
        output_path = output_dir / filename
        generate_schema(model_class, output_path)
        print(f"  - {filename}")

    print("\nDone. Review the changes and commit if correct:")
    print("  git diff spec/draft/")


if __name__ == "__main__":
    main()
