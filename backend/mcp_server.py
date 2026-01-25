"""MCP (Model Context Protocol) server for ASP Web UI.

This server exposes the current UI context to AI agents via MCP,
allowing them to understand what the user is viewing/editing.
"""

import json
from pathlib import Path
from typing import Any

# MCP context state (updated by the frontend via API)
_mcp_state: dict[str, Any] = {
    "focus": {
        "focusedDecision": None,
        "focusedOption": None,
        "panelState": "collapsed",
    },
    "analysis": None,
    "selectedDecision": None,
}


def get_mcp_context() -> dict[str, Any]:
    """Get the current MCP context."""
    return _mcp_state.copy()


def update_mcp_context(updates: dict[str, Any]) -> None:
    """Update the MCP context from the frontend."""
    global _mcp_state
    _mcp_state.update(updates)


def build_context_from_analysis(
    analysis: dict[str, Any],
    file_path: str | None = None,
    focus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build MCP context from an analysis dict.

    Args:
        analysis: The analysis specification dict.
        file_path: Path to the analysis file.
        focus: Current focus state from the UI.

    Returns:
        MCP context dict.
    """
    context: dict[str, Any] = {
        "focus": focus or {
            "focusedDecision": None,
            "focusedOption": None,
            "panelState": "collapsed",
        },
        "analysis": None,
        "selectedDecision": None,
    }

    if analysis:
        analysis_content = analysis.get("analysis", {})
        decisions = analysis.get("decisions", {})

        context["analysis"] = {
            "name": analysis_content.get("name", "Untitled"),
            "version": analysis.get("version", "1.0"),
            "decisionCount": len(decisions),
            "currentLOD": 5,  # Default to show all
            "filePath": file_path,
            "isDirty": False,
        }

        # If there's a focused decision, include its details
        focused_id = context["focus"].get("focusedDecision")
        if focused_id and focused_id in decisions:
            decision = decisions[focused_id]
            context["selectedDecision"] = {
                "id": focused_id,
                "label": decision.get("label", focused_id),
                "type": decision.get("type", "method"),
                "importance": decision.get("importance", 3),
                "rationale": decision.get("rationale"),
                "default": decision.get("default"),
                "options": [
                    {
                        "id": opt_id,
                        "label": opt.get("label", opt_id),
                        "description": opt.get("description"),
                        "isDefault": decision.get("default") == opt_id,
                        "hasEvidence": bool(opt.get("evidence")),
                        "hasConstraints": bool(
                            opt.get("incompatible_with") or opt.get("requires")
                        ),
                    }
                    for opt_id, opt in decision.get("options", {}).items()
                ],
            }

    return context


# MCP resource handlers for integration with MCP protocol
def handle_mcp_resource(uri: str) -> dict[str, Any]:
    """Handle an MCP resource request.

    Args:
        uri: The resource URI (e.g., "asp://context/focus")

    Returns:
        The resource content.
    """
    context = get_mcp_context()

    if uri == "asp://context/focus":
        return context.get("focus", {})
    elif uri == "asp://analysis/current":
        return context.get("analysis") or {"error": "No analysis loaded"}
    elif uri.startswith("asp://decision/"):
        decision_id = uri.split("/")[-1]
        selected = context.get("selectedDecision")
        if selected and selected.get("id") == decision_id:
            return selected
        return {"error": f"Decision {decision_id} not found or not focused"}

    return {"error": f"Unknown resource: {uri}"}


def handle_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle an MCP tool call.

    Args:
        name: The tool name (e.g., "asp://edit/decision")
        arguments: The tool arguments.

    Returns:
        The tool result.
    """
    if name == "asp://edit/decision":
        # This would queue an edit for user approval
        return {
            "status": "pending",
            "message": "Edit proposal queued for user approval",
            "proposal": arguments,
        }

    return {"error": f"Unknown tool: {name}"}
