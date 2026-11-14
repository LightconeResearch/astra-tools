"""Insights and evidence: every entry of `Option.insights` names a prior insight of the
analysis (`INVALID_INSIGHT_REF`)."""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context

CODES = frozenset({"INVALID_INSIGHT_REF"})


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for decision_id, decision in analysis.decisions.items():
            for option_id, option in decision.options.items():
                for index, id_ in enumerate(option.insights):
                    if id_ in analysis.prior_insights:
                        continue
                    detail = (
                        "it is a finding, and an option cites only prior insights"
                        if id_ in analysis.findings
                        else "this analysis has no prior insight of that id"
                    )
                    message = f"`{id_}` names no prior insight: {detail}"
                    pointer = ("decisions", decision_id, "options", option_id, "insights", index)
                    at = context.at(member.identity, pointer)
                    yield context.diagnostic("INVALID_INSIGHT_REF", message, at)
