"""Analysis API endpoints."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from asp.helpers import load_yaml, save_yaml


router = APIRouter()


class UniverseMeta(BaseModel):
    """Metadata about a universe file."""

    id: str
    description: str | None
    path: str


class AnalysisResponse(BaseModel):
    """Response for loading an analysis."""

    analysis: dict[str, Any]
    filePath: str
    universes: list[UniverseMeta]


class SaveRequest(BaseModel):
    """Request body for saving an analysis."""

    analysis: dict[str, Any]


class SaveResponse(BaseModel):
    """Response for saving an analysis."""

    savedAt: str
    success: bool


def find_analysis_file(work_dir: Path) -> Path | None:
    """Find the analysis file in the working directory.

    Looks for asp.yaml, analysis.yaml, or any .yaml file.
    """
    candidates = ["asp.yaml", "analysis.yaml"]

    for name in candidates:
        path = work_dir / name
        if path.exists():
            return path

    # Fall back to first yaml file
    yaml_files = list(work_dir.glob("*.yaml"))
    if yaml_files:
        return yaml_files[0]

    return None


def find_universes(work_dir: Path) -> list[UniverseMeta]:
    """Find universe files in the universes/ subdirectory."""
    universes_dir = work_dir / "universes"
    if not universes_dir.is_dir():
        return []

    universes = []
    for path in universes_dir.glob("*.yaml"):
        try:
            data = load_yaml(path)
            universe_content = data.get("universe", {})
            universes.append(
                UniverseMeta(
                    id=path.stem,
                    description=universe_content.get("description"),
                    path=str(path.relative_to(work_dir)),
                )
            )
        except Exception:
            # Skip invalid universe files
            continue

    return universes


@router.get("/analysis", response_model=AnalysisResponse)
async def get_analysis(request: Request, path: str | None = None):
    """Load an analysis file.

    Args:
        path: Optional specific path to load. If not provided,
              searches the working directory for asp.yaml.
    """
    work_dir: Path = request.app.state.work_dir

    if path:
        analysis_path = Path(path)
        if not analysis_path.is_absolute():
            analysis_path = work_dir / path
    else:
        analysis_path = find_analysis_file(work_dir)

    if not analysis_path or not analysis_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No analysis file found in {work_dir}",
        )

    try:
        analysis = load_yaml(analysis_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load analysis: {e}",
        )

    universes = find_universes(work_dir)

    return AnalysisResponse(
        analysis=analysis,
        filePath=str(analysis_path),
        universes=universes,
    )


@router.put("/analysis", response_model=SaveResponse)
async def save_analysis(request: Request, body: SaveRequest):
    """Save an analysis file.

    Saves to the same path that was loaded.
    """
    work_dir: Path = request.app.state.work_dir
    analysis_path = find_analysis_file(work_dir)

    if not analysis_path:
        # Create new file
        analysis_path = work_dir / "asp.yaml"

    try:
        save_yaml(body.analysis, analysis_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save analysis: {e}",
        )

    return SaveResponse(
        savedAt=datetime.now().isoformat(),
        success=True,
    )
