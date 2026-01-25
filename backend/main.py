"""FastAPI backend for ASP Web UI.

This server provides REST API endpoints for loading, validating,
and saving ASP analysis specifications.
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add the src directory to the path so we can import asp
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.analysis import router as analysis_router
from api.validation import router as validation_router
from api.universes import router as universes_router
from api.mcp import router as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: set the working directory from env or use current
    work_dir = os.environ.get("ASP_WORK_DIR", os.getcwd())
    app.state.work_dir = Path(work_dir)
    print(f"ASP Backend started. Working directory: {app.state.work_dir}")
    yield
    # Shutdown
    print("ASP Backend shutting down.")


app = FastAPI(
    title="ASP Web UI Backend",
    description="REST API for ASP analysis specifications",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis_router, prefix="/api", tags=["analysis"])
app.include_router(validation_router, prefix="/api", tags=["validation"])
app.include_router(universes_router, prefix="/api", tags=["universes"])
app.include_router(mcp_router, prefix="/api", tags=["mcp"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "ASP Web UI Backend"}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
