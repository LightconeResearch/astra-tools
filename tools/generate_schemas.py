#!/usr/bin/env python
"""Generate JSON schemas from Pydantic models into spec/draft/.

This script reads the Pydantic models from the top-level models/ directory
and generates JSON schemas in spec/draft/. These schemas are then bundled
into the astra package at build time.

Usage:
    python tools/generate_schemas.py

The generated schemas are:
    - spec/draft/analysis.schema.json
    - spec/draft/universe.schema.json
    - spec/draft/insights.schema.json
"""

import argparse
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


def _inline_root_ref(schema: dict) -> dict:
    """Inline a root $ref into the top-level schema.

    Pydantic self-referencing models produce schemas like:
        {"$defs": {"Model": {...}}, "$ref": "#/$defs/Model"}

    This hoists the referenced definition's properties to the root level
    while keeping $defs for recursive references.
    """
    if "$ref" not in schema:
        return schema

    ref = schema["$ref"]  # e.g., "#/$defs/Analysis"
    def_name = ref.split("/")[-1]
    defs = schema.get("$defs", {})

    if def_name not in defs:
        return schema

    root_def = dict(defs[def_name])
    result = dict(root_def)
    # Keep $defs for recursive references (e.g., analyses references Analysis)
    result["$defs"] = defs
    return result


def main() -> None:
    """Generate JSON schemas from Pydantic models."""
    parser = argparse.ArgumentParser(description="Generate JSON schemas from Pydantic models")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SPEC_DIR,
        help=f"Output directory (default: {SPEC_DIR})",
    )
    args = parser.parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    schemas = {
        "analysis.schema.json": _inline_root_ref(
            Analysis.model_json_schema(mode="serialization")
        ),
        "universe.schema.json": _inline_root_ref(
            Universe.model_json_schema(mode="serialization")
        ),
        "insights.schema.json": _inline_root_ref(
            InsightCollection.model_json_schema(mode="serialization")
        ),
    }

    for name, schema in schemas.items():
        output_path = output_dir / name
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        print(f"Generated {output_path}")

    print(f"\nAll schemas generated in {output_dir}")


if __name__ == "__main__":
    main()
