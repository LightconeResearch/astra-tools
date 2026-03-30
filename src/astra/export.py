"""Export ASTRA YAML analyses to RO-Crate format.

Transforms a validated `astra.yaml` dict into an RO-Crate directory
with `ro-crate-metadata.json`, using the ASTRACrate class as the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astra.crate import ASTRACrate


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

    # Inputs
    for inp in analysis.get("inputs") or []:
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

    # Outputs
    for out in analysis.get("outputs") or []:
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

    # Decisions
    for dec_name, dec in (analysis.get("decisions") or {}).items():
        if dec.get("delegates_to"):
            parent_ref = dec["delegates_to"]
            # Convert ../parent_decision to ../#decision/parent_decision
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

    # Prior insights
    for name, insight in (analysis.get("prior_insights") or {}).items():
        _add_insight(crate, name, insight, is_finding=False)

    # Findings
    for name, finding in (analysis.get("findings") or {}).items():
        _add_insight(crate, name, finding, is_finding=True)

    # Success criteria
    for criterion in analysis.get("success_criteria") or []:
        crate.add_success_criterion(
            claim=criterion["claim"],
            output=criterion.get("output"),
            condition=criterion.get("condition"),
        )

    # Sub-analyses -> subcrates
    for sub_name, sub_data in (analysis.get("analyses") or {}).items():
        sub_crate = crate.add_subcrate(
            name=sub_name,
            analysis_name=sub_data.get("label", sub_name),
            description=sub_data.get("description"),
            version=sub_data.get("astra_version", "1.0"),
        )
        _populate_subcrate(sub_crate, sub_data)

    # Universes
    for uni_name, uni_data in (analysis.get("universes") or {}).items():
        selections = _parse_selections(uni_data.get("selections") or [], analysis)
        crate.add_universe(
            name=uni_name,
            selections=selections,
            description=uni_data.get("description"),
        )

    return crate


def _populate_subcrate(crate: ASTRACrate, data: dict[str, Any]) -> None:
    """Populate a subcrate with data from a sub-analysis dict."""
    for inp in data.get("inputs") or []:
        crate.add_input(
            name=inp["name"],
            input_type=inp["type"],
            description=inp.get("description"),
            source=inp.get("source"),
            input_from=inp.get("input_from"),
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
                options[opt_name] = opt_dict
            crate.add_decision(
                name=dec_name,
                label=dec.get("label", dec_name),
                options=options,
                default=dec.get("default"),
                rationale=dec.get("description") or dec.get("rationale"),
            )


def _add_insight(
    crate: ASTRACrate, name: str, data: dict[str, Any], *, is_finding: bool
) -> None:
    """Add an insight to the crate."""
    evidence_list = []
    for ev in data.get("evidence") or []:
        ev_dict: dict[str, Any] = {"id": ev["id"]}
        if "doi" in ev:
            ev_dict["doi"] = ev["doi"]
        if "version" in ev:
            ev_dict["version"] = ev["version"]
        if "artifact" in ev:
            ev_dict["artifact"] = ev["artifact"]
        if "source_commit" in ev:
            ev_dict["source_commit"] = ev["source_commit"]
        if "snapshot" in ev:
            ev_dict["snapshot"] = ev["snapshot"]
        if "checksum" in ev:
            ev_dict["checksum"] = ev["checksum"]
        if "quote" in ev:
            ev_dict["quote"] = ev["quote"]
        if "figure" in ev:
            ev_dict["figure"] = ev["figure"]
        if "table" in ev:
            ev_dict["table"] = ev["table"]
        if "location" in ev:
            ev_dict["location"] = ev["location"]
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
    analysis: dict[str, Any],
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
        # Cross-sub-analysis paths: "sub/method" -> "sub/#decision/method"
        if "/" in dec_path:
            parts = dec_path.rsplit("/", 1)
            sub_path = parts[0]
            dec_name = parts[1]
            dec_id = f"{sub_path}/#decision/{dec_name}"
            opt_id = f"{sub_path}/#decision/{dec_name}/option/{opt_name}"
        else:
            dec_id = f"#decision/{dec_path}"
            opt_id = f"#decision/{dec_path}/option/{opt_name}"
        result[dec_id] = opt_id

    return result
