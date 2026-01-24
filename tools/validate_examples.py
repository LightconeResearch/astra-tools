#!/usr/bin/env python3
"""Validate all example files in examples/.

This script validates:
- examples/valid/ - Files that MUST pass validation
- examples/invalid/ - Files that MUST fail validation

Usage:
    python tools/validate_examples.py
    # or
    make validate
"""

from pathlib import Path
import subprocess
import sys


def main():
    project_root = Path(__file__).parent.parent
    examples_dir = project_root / "examples"

    valid_dir = examples_dir / "valid"
    invalid_dir = examples_dir / "invalid"

    errors = []

    # Validate valid examples
    print("Validating examples/valid/...")
    for asp_yaml in valid_dir.rglob("asp.yaml"):
        print(f"  ✓ {asp_yaml.relative_to(project_root)}")
        result = subprocess.run(
            ["asp", "validate", str(asp_yaml)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            errors.append(f"{asp_yaml}: Should pass but failed:\n{result.stderr}")

        # Also validate universe files
        universes_dir = asp_yaml.parent / "universes"
        if universes_dir.exists():
            for universe_yaml in universes_dir.glob("*.yaml"):
                print(f"    ✓ {universe_yaml.relative_to(project_root)}")
                result = subprocess.run(
                    ["asp", "validate", str(universe_yaml), "-a", str(asp_yaml)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    errors.append(f"{universe_yaml}: Should pass but failed:\n{result.stderr}")

    # Validate standalone valid files
    for yaml_file in ["minimal.yaml", "full.yaml"]:
        file_path = valid_dir / yaml_file
        if file_path.exists():
            print(f"  ✓ {file_path.relative_to(project_root)}")
            result = subprocess.run(
                ["asp", "validate", str(file_path)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                errors.append(f"{file_path}: Should pass but failed:\n{result.stderr}")

    print()

    # Validate invalid examples
    print("Checking examples/invalid/ properly fail...")
    for yaml_file in invalid_dir.glob("*.yaml"):
        result = subprocess.run(
            ["asp", "validate", str(yaml_file)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            errors.append(f"{yaml_file}: Should fail but passed")
            print(f"  ✗ {yaml_file.relative_to(project_root)} (should have failed)")
        else:
            print(f"  ✓ {yaml_file.relative_to(project_root)} (correctly failed)")

    print()

    if errors:
        print("ERRORS:")
        for error in errors:
            print(f"  {error}")
        sys.exit(1)
    else:
        print("All examples validated successfully.")


if __name__ == "__main__":
    main()
