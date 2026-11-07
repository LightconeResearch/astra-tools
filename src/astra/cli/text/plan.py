"""The plan as text: each planned result, each after what it reads, with its places and the
command run in its analysis's folder, its placeholders filled in (§11), or the commit whose
record it is read through (§17)."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import console
from astra.plan import Plan, render_command


def show(plan: Plan) -> None:
    out = console()
    for result in plan.results:
        out.print(Text(", ".join(place.address for place in result.places), style="bold"))
        at = "" if result.owner.commit is None else f" at {result.owner.commit}"
        for place in result.places:
            out.print(Text(f"  record   {place.record}{at}"))
            out.print(Text(f"  bytes    {place.bytes}{at}"))
        if result.read_only:
            out.print(Text(f"  read through its record{at}", style="dim"))
            continue
        folder = result.workdir or "."
        run_at = "" if result.run_at is None else f" at {result.run_at}"
        out.print(Text(f"  run in   {folder}{run_at}"))
        out.print(Text(f"  command  {render_command(result, folder)}"))
    out.print(Text(f"{len(plan.results)} planned result(s)"))
