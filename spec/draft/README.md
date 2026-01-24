# ASP Specification - Draft

This directory contains the working draft of the ASP JSON Schema specification.

## Files

- `analysis.schema.json` - Schema for ASP analysis specifications (`asp.yaml`)
- `universe.schema.json` - Schema for universe specifications
- `insights.schema.json` - Schema for insight collections (future)

## Versioning

When a version is released:

1. This `draft/` directory is copied to a versioned directory (e.g., `v1.0/`)
2. The versioned schemas are immutable and represent the official specification
3. The `draft/` directory continues to evolve for the next version

## Regenerating Schemas

Schemas are generated from Pydantic models. To regenerate:

```bash
make schemas
# or
asp schema export -o spec/draft/
```

**Important**: Schema changes should be reviewed in PRs. Run `make schemas` locally
and commit the changes so they can be reviewed.

## Source of Truth

- **Pydantic models** (`src/asp/models/`) are the authoring source
- **JSON Schemas** (this directory) are the versioned contract

Other implementations can target the JSON Schema without depending on Python.
