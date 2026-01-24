#!/usr/bin/env python
"""Generate JSON schemas from Pydantic models into spec/draft/.

This script reads the Pydantic models from the top-level models/ directory
and generates JSON schemas in spec/draft/. These schemas are then bundled
into the asp package at build time.

Usage:
    python tools/generate_schemas.py

The generated schemas are:
    - spec/draft/analysis.schema.json
    - spec/draft/universe.schema.json
    - spec/draft/insights.schema.json
"""

import json
import sys
from pathlib import Path

# Add the repository root to the path so we can import from models/
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from models.analysis import Analysis
from models.insight import InsightCollection
from models.universe import Universe

SPEC_DIR = REPO_ROOT / "spec" / "draft"


def main() -> None:
    """Generate JSON schemas from Pydantic models."""
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    schemas = {
        "analysis.schema.json": Analysis.model_json_schema(mode="serialization"),
        "universe.schema.json": Universe.model_json_schema(mode="serialization"),
        "insights.schema.json": InsightCollection.model_json_schema(mode="serialization"),
    }

    for name, schema in schemas.items():
        output_path = SPEC_DIR / name
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        print(f"Generated {output_path}")

    print(f"\nAll schemas generated in {SPEC_DIR}")


if __name__ == "__main__":
    main()
