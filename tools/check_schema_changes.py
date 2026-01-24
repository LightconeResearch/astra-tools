#!/usr/bin/env python3
"""Check if schemas in spec/draft/ are in sync with Pydantic models.

This script compares the committed schemas with freshly generated ones.
Used by CI to ensure schema changes are committed.

Usage:
    python tools/check_schema_changes.py
    # or
    make check-schemas

Exit codes:
    0 - Schemas are in sync
    1 - Schemas are out of sync (need to run 'make schemas')

Note: This tool imports directly from models/, NOT from asp/.
"""

import json
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.analysis import Analysis
from models.universe import Universe
from models.insight import InsightCollection


def generate_schema(model_class) -> dict:
    """Generate JSON schema from a Pydantic model."""
    return model_class.model_json_schema(mode="serialization")


def main():
    spec_dir = project_root / "spec" / "draft"

    # Schema definitions
    schemas = [
        (Analysis, "analysis.schema.json"),
        (Universe, "universe.schema.json"),
        (InsightCollection, "insights.schema.json"),
    ]

    out_of_sync = []

    for model_class, filename in schemas:
        committed_path = spec_dir / filename

        if not committed_path.exists():
            out_of_sync.append(f"{filename}: Missing (not committed)")
            continue

        # Load committed schema
        with open(committed_path) as f:
            committed_data = json.load(f)

        # Generate fresh schema
        generated_data = generate_schema(model_class)

        # Remove version comment for comparison (it may change)
        committed_data.pop("$comment", None)
        generated_data.pop("$comment", None)

        if committed_data != generated_data:
            out_of_sync.append(f"{filename}: Out of sync with models")

    if out_of_sync:
        print("Schema sync check FAILED:")
        for msg in out_of_sync:
            print(f"  ❌ {msg}")
        print()
        print("Run 'make schemas' and commit the changes.")
        sys.exit(1)
    else:
        print("Schema sync check PASSED:")
        print("  ✅ All schemas are in sync with models")
        sys.exit(0)


if __name__ == "__main__":
    main()
