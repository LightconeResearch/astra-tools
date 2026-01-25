"""Validation API endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from asp.validation.schema import validate_against_schema, get_analysis_schema
from asp.validation.semantic import validate_analysis


router = APIRouter()


class ValidationError(BaseModel):
    """A validation error."""

    path: str
    message: str
    type: str  # "schema" or "semantic"


class ValidateRequest(BaseModel):
    """Request body for validation."""

    analysis: dict[str, Any]


class ValidationResponse(BaseModel):
    """Response for validation."""

    valid: bool
    schemaErrors: list[ValidationError]
    semanticErrors: list[ValidationError]


@router.post("/validate", response_model=ValidationResponse)
async def validate(body: ValidateRequest):
    """Validate an analysis specification.

    Performs both schema validation and semantic validation.
    """
    schema_errors: list[ValidationError] = []
    semantic_errors: list[ValidationError] = []

    # Schema validation
    try:
        schema = get_analysis_schema()
        raw_errors = validate_against_schema(body.analysis, schema)
        for error_msg in raw_errors:
            # Parse the error message format: "path: message"
            if ": " in error_msg:
                path, message = error_msg.split(": ", 1)
            else:
                path = "(root)"
                message = error_msg
            schema_errors.append(
                ValidationError(path=path, message=message, type="schema")
            )
    except Exception as e:
        schema_errors.append(
            ValidationError(
                path="(schema)",
                message=f"Schema validation failed: {e}",
                type="schema",
            )
        )

    # Semantic validation (only if schema is valid)
    if not schema_errors:
        try:
            raw_semantic_errors = validate_analysis(body.analysis)
            for err in raw_semantic_errors:
                semantic_errors.append(
                    ValidationError(
                        path=err.path or "(root)",
                        message=err.message,
                        type="semantic",
                    )
                )
        except Exception as e:
            semantic_errors.append(
                ValidationError(
                    path="(semantic)",
                    message=f"Semantic validation failed: {e}",
                    type="semantic",
                )
            )

    return ValidationResponse(
        valid=len(schema_errors) == 0 and len(semantic_errors) == 0,
        schemaErrors=schema_errors,
        semanticErrors=semantic_errors,
    )
