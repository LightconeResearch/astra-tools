"""The check report as text: each place of each planned result, as its record's file, with its
address and statuses, then why, as `line:col level CODE message`, and what each environment
scheme answered for its record's environment; then the evidence, grouped under the root's
astra.yaml, as `validate`'s report is grouped by file."""

from __future__ import annotations

from types import MappingProxyType

from rich.text import Text

from astra.check import CheckReport, Reason
from astra.cli.text import console, rule_line

_STYLES = MappingProxyType(
    {
        "unchanged": "green",
        "stale": "yellow",
        "missing": "red",
        "present": "green",
        "absent": "yellow",
    }
)


def show(report: CheckReport) -> None:
    out = console()
    counts = dict.fromkeys(("unchanged", "stale", "missing", "absent"), 0)
    for checked in report.results:
        commit = checked.result.owner.commit
        for status in checked.statuses:
            record = status.place.record if commit is None else f"{status.place.record} at {commit}"
            line = Text(record, style="bold")
            line.append(f"  {status.place.address}  ")
            line.append(status.record_status, style=_STYLES[status.record_status])
            counts[status.record_status] += 1
            if status.bytes_status is not None:
                line.append("  ")
                line.append(status.bytes_status, style=_STYLES[status.bytes_status])
                counts["absent"] += status.bytes_status == "absent"
            if status.record is not None and not status.committed:
                line.append("  not committed", style="dim")
            out.print(line)
            for reason in status.reasons:
                out.print(_reason(reason))
            for answer in status.environment:
                assert status.record is not None  # only a record's environment is answered for
                can = "can be recreated" if answer.recreatable else "can't be recreated"
                out.print(Text(f"  {answer.scheme}: {status.record.environment} {can}"))
                for held in answer.holds.splitlines():
                    out.print(Text(f"    {held}"))
    if report.evidence:
        out.print(Text(report.root, style="bold"))
    for evidence in report.evidence:
        if evidence.reasons:
            for reason in evidence.reasons:
                out.print(_reason(reason))
        else:
            where = evidence.location
            out.print(f"  {where.line}:{where.column} unchanged `{evidence.artifact}`")
    results = sum(len(checked.statuses) for checked in report.results)
    at = "" if report.at == "worktree" else f" at {report.at}"
    out.print(
        f"{report.root}{at}: {results} place(s) of planned results, {counts['unchanged']} "
        f"unchanged, {counts['stale']} stale, {counts['missing']} missing; "
        f"{counts['absent']} absent"
    )


def _reason(reason: Reason) -> Text:
    return rule_line(reason.location, reason.level, reason.code, reason.message, reason.breaks)
