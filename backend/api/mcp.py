"""MCP API endpoints."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mcp_server import (
    get_mcp_context,
    update_mcp_context,
    handle_mcp_resource,
    handle_mcp_tool,
    build_context_from_analysis,
)
from asp.helpers import load_yaml
from api.analysis import find_analysis_file


router = APIRouter()


class UpdateContextRequest(BaseModel):
    """Request to update MCP context from frontend."""

    focus: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    selectedDecision: dict[str, Any] | None = None


class MCPResourceRequest(BaseModel):
    """Request for an MCP resource."""

    uri: str


class MCPToolRequest(BaseModel):
    """Request to call an MCP tool."""

    name: str
    arguments: dict[str, Any]


@router.get("/mcp/context")
async def get_context(request: Request):
    """Get the current MCP context.

    This endpoint returns the current state of the UI for agent consumption.
    If no context has been pushed from the frontend, it builds context
    from the loaded analysis file.
    """
    context = get_mcp_context()

    # If no analysis in context, try to load from file
    if context.get("analysis") is None:
        work_dir = request.app.state.work_dir
        analysis_path = find_analysis_file(work_dir)
        if analysis_path and analysis_path.exists():
            try:
                analysis = load_yaml(analysis_path)
                context = build_context_from_analysis(
                    analysis,
                    str(analysis_path),
                    context.get("focus"),
                )
            except Exception:
                pass

    return context


@router.put("/mcp/context")
async def update_context(body: UpdateContextRequest):
    """Update the MCP context from the frontend.

    The frontend calls this to sync its state with the MCP server.
    """
    updates = {}
    if body.focus is not None:
        updates["focus"] = body.focus
    if body.analysis is not None:
        updates["analysis"] = body.analysis
    if body.selectedDecision is not None:
        updates["selectedDecision"] = body.selectedDecision

    update_mcp_context(updates)
    return {"status": "ok", "updated": list(updates.keys())}


@router.post("/mcp/resource")
async def get_resource(body: MCPResourceRequest):
    """Get an MCP resource by URI.

    Resources are read-only views into the current state.
    """
    return handle_mcp_resource(body.uri)


@router.post("/mcp/tool")
async def call_tool(body: MCPToolRequest):
    """Call an MCP tool.

    Tools can modify state (with user approval).
    """
    return handle_mcp_tool(body.name, body.arguments)
