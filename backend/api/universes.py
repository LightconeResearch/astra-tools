"""Universes API endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from asp.helpers import load_yaml


router = APIRouter()


class UniverseMeta(BaseModel):
    """Metadata about a universe file."""

    id: str
    description: str | None
    path: str


class UniversesResponse(BaseModel):
    """Response for listing universes."""

    universes: list[UniverseMeta]


class UniverseDecisionsResponse(BaseModel):
    """Response for getting universe decisions."""

    decisions: dict[str, str]


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


@router.get("/universes", response_model=UniversesResponse)
async def list_universes(request: Request):
    """List available universe files."""
    work_dir: Path = request.app.state.work_dir
    universes = find_universes(work_dir)
    return UniversesResponse(universes=universes)


@router.get("/universes/{universe_id}", response_model=UniverseDecisionsResponse)
async def get_universe(request: Request, universe_id: str):
    """Get the decisions from a specific universe."""
    work_dir: Path = request.app.state.work_dir
    universe_path = work_dir / "universes" / f"{universe_id}.yaml"

    if not universe_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Universe '{universe_id}' not found",
        )

    try:
        data = load_yaml(universe_path)
        universe_content = data.get("universe", {})
        decisions = universe_content.get("decisions", {})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load universe: {e}",
        )

    return UniverseDecisionsResponse(decisions=decisions)
