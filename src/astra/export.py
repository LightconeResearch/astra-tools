"""Export ASTRA YAML analyses to RO-Crate format.

Transforms a validated `astra.yaml` dict into an RO-Crate directory
with `ro-crate-metadata.json`, using the ASTRACrate class as the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astra.crate import ASTRACrate

_EVIDENCE_KEYS = (
    "doi",
    "version",
    "artifact",
    "source_commit",
    "snapshot",
    "checksum",
    "quote",
    "figure",
    "table",
    "location",
)


def export_rocrate(analysis: dict[str, Any], output_dir: str | Path) -> None:
    """Export an ASTRA analysis dict to RO-Crate format.

    Args:
        analysis: Analysis data loaded from astra.yaml.
        output_dir: Directory to write the RO-Crate to.
    """
    crate = _build_crate(analysis)
    crate.write(str(output_dir))


def _build_crate(analysis: dict[str, Any]) -> ASTRACrate:
    """Build an ASTRACrate from a YAML analysis dict."""
    crate = ASTRACrate(
        name=analysis["name"],
        version=analysis.get("astra_version", "1.0"),
        description=analysis.get("description"),
        authors=analysis.get("authors"),
        keywords=analysis.get("tags"),
        container=analysis.get("container"),
    )

    _populate_crate(crate, analysis)

    for name, insight in (analysis.get("prior_insights") or {}).items():
        _add_insight(crate, name, insight, is_finding=False)

    for name, finding in (analysis.get("findings") or {}).items():
        _add_insight(crate, name, finding, is_finding=True)

    for criterion in analysis.get("success_criteria") or []:
        crate.add_success_criterion(
            claim=criterion["claim"],
            output=criterion.get("output"),
            condition=criterion.get("condition"),
        )

    for sub_name, sub_data in (analysis.get("analyses") or {}).items():
        sub_crate = crate.add_subcrate(
            name=sub_name,
            analysis_name=sub_data.get("label", sub_name),
            description=sub_data.get("description"),
            version=sub_data.get("astra_version", "1.0"),
        )
        _populate_crate(sub_crate, sub_data)

    for uni_name, uni_data in (analysis.get("universes") or {}).items():
        selections = _parse_selections(uni_data.get("selections") or [])
        crate.add_universe(
            name=uni_name,
            selections=selections,
            description=uni_data.get("description"),
        )

    return crate


def _populate_crate(crate: ASTRACrate, data: dict[str, Any]) -> None:
    """Populate a crate (root or subcrate) with inputs, outputs, and decisions."""
    for inp in data.get("inputs") or []:
        crate.add_input(
            name=inp["name"],
            input_type=inp["type"],
            description=inp.get("description"),
            source=inp.get("source"),
            input_from=inp.get("input_from"),
            analysis_ref=inp.get("based_on"),
            ref_version=inp.get("ref_version"),
            use_outputs=inp.get("use_outputs"),
            checksum=inp.get("checksum"),
        )

    for out in data.get("outputs") or []:
        recipe = out.get("recipe")
        crate.add_output(
            name=out["name"],
            output_type=out["type"],
            description=out.get("description"),
            output_from=out.get("output_from"),
            active_when=out.get("active_when"),
            recipe_command=recipe.get("command") if recipe else None,
            recipe_inputs=recipe.get("depends_on") if recipe else None,
            recipe_container=recipe.get("container") if recipe else None,
            recipe_resources=recipe.get("resources") if recipe else None,
        )

    for dec_name, dec in (data.get("decisions") or {}).items():
        if dec.get("delegates_to"):
            parent_ref = dec["delegates_to"]
            if parent_ref.startswith("../"):
                parent_ref = f"../#decision/{parent_ref[3:]}"
            crate.add_delegated_decision(dec_name, parent_ref)
        else:
            options: dict[str, dict[str, Any]] = {}
            for opt_name, opt in (dec.get("options") or {}).items():
                opt_dict: dict[str, Any] = {"label": opt.get("label", opt_name)}
                if opt.get("description"):
                    opt_dict["description"] = opt["description"]
                if opt.get("incompatible_with"):
                    opt_dict["incompatible_with"] = opt["incompatible_with"]
                if opt.get("requires"):
                    opt_dict["requires"] = opt["requires"]
                if opt.get("insights"):
                    opt_dict["insights"] = opt["insights"]
                if opt.get("is_excluded"):
                    opt_dict["excluded"] = True
                if opt.get("excluded_reason"):
                    opt_dict["excluded_reason"] = opt["excluded_reason"]
                options[opt_name] = opt_dict
            crate.add_decision(
                name=dec_name,
                label=dec.get("label", dec_name),
                options=options,
                default=dec.get("default"),
                rationale=dec.get("description") or dec.get("rationale"),
                tags=dec.get("tags"),
                active_when=dec.get("active_when"),
            )


def _add_insight(crate: ASTRACrate, name: str, data: dict[str, Any], *, is_finding: bool) -> None:
    """Add an insight to the crate."""
    evidence_list = []
    for ev in data.get("evidence") or []:
        ev_dict: dict[str, Any] = {"id": ev["id"]}
        for key in _EVIDENCE_KEYS:
            if key in ev:
                ev_dict[key] = ev[key]
        evidence_list.append(ev_dict)

    crate.add_insight(
        name=name,
        claim=data["claim"],
        evidence_list=evidence_list,
        is_finding=is_finding,
        derived=data.get("is_derived", False),
        scope=data.get("scope"),
        tags=data.get("tags"),
        notes=data.get("notes"),
    )


def _parse_selections(
    selections: list[dict[str, str]] | dict[str, str],
) -> dict[str, str]:
    """Parse universe selections into {decision_@id: option_@id} dict for ASTRACrate.

    Input: list of {decision: "name", option: "name"} or flat dict {decision: option}.
    Output: dict mapping full @id paths for ASTRACrate.add_universe().
    """
    if isinstance(selections, dict):
        items = list(selections.items())
    else:
        items = [(s["decision"], s["option"]) for s in selections]

    result: dict[str, str] = {}
    for dec_path, opt_name in items:
        if "/" in dec_path:
            sub_path, dec_name = dec_path.rsplit("/", 1)
            dec_id = f"{sub_path}/#decision/{dec_name}"
            opt_id = f"{sub_path}/#decision/{dec_name}/option/{opt_name}"
        else:
            dec_id = f"#decision/{dec_path}"
            opt_id = f"#decision/{dec_path}/option/{opt_name}"
        result[dec_id] = opt_id

    return result
