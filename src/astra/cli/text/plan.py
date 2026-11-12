"""The plan as text: each planned result, each after what it reads, with its places, what its
recipe asks for and the command run in its analysis's folder, its placeholders filled in (§11),
or the commit whose record it is read through (§17); then the plan's notes, counted by kind and,
on request, each one (design §4.6). The notes counted and listed are those that concern what the
root builds (`Note.built`); for `fallback_pin`, `unplanned` and `outside_folder`, a line gives the
whole stack's count where it is more."""

from __future__ import annotations

from dataclasses import asdict
from typing import get_args

from rich.text import Text

from astra.cli.text import console
from astra.plan import Note, NoteKind, Plan, render_command


def show(plan: Plan, *, listed: bool = False) -> None:
    """`plan` as text: its results, then its notes counted by kind, and each one where
    `listed`."""
    out = console()
    for result in plan.results:
        out.print(Text(", ".join(place.address for place in result.places), style="bold"))
        at = "" if result.owner.commit is None else f" at {result.owner.commit}"
        for place in result.places:
            out.print(Text(f"  record    {place.record}{at}"))
            out.print(Text(f"  bytes     {place.bytes}{at}"))
        if result.read_only:
            out.print(Text(f"  read through its record{at}", style="dim"))
            continue
        folder = result.workdir or "."
        run_at = "" if result.run_at is None else f" at {result.run_at}"
        out.print(Text(f"  run in    {folder}{run_at}"))
        if result.resources is not None:
            asked = asdict(result.resources).items()
            shown = ", ".join(f"{key} {value}" for key, value in asked if value is not None)
            out.print(Text(f"  resources {shown}"))
        out.print(Text(f"  command   {render_command(result, folder)}"))
    counted = [note for note in plan.notes if note.built]
    if listed:
        for note in counted:
            where = note.location
            line = Text("note", style="cyan")
            if where is not None:
                line.append(f" {where.file}:{where.line}:{where.column}")
            line.append(f" {note.message}")
            out.print(line)
    if not plan.notes:
        out.print(Text(f"{len(plan.results)} planned result(s)"))
        return
    hint = "" if listed or not counted else " (--notes lists them)"
    out.print(
        Text(f"{len(plan.results)} planned result(s), and notes, none of them a breach{hint}:")
    )
    for kind in get_args(NoteKind):
        notes = [note for note in counted if note.kind == kind]
        if notes:
            out.print(Text(f"  {_counted(kind, notes)}"))
        whole = sum(note.kind == kind for note in plan.notes)
        if whole > len(notes) and kind == "fallback_pin":
            out.print(
                Text(
                    f"  {whole} pin(s) in the whole stack name another analysis's universe only "
                    "because their file has none of that id"
                )
            )
        if whole > len(notes) and kind == "unplanned":
            out.print(Text(f"  {whole} output(s) in the whole stack have no planned result"))
        if whole > len(notes) and kind == "outside_folder":
            out.print(
                Text(f"  {whole} command(s) in the whole stack name a path outside their analysis")
            )


def _counted(kind: NoteKind, notes: list[Note]) -> str:
    """The notes of `kind`, counted."""
    if kind == "fallback_pin":
        return (
            f"{len(notes)} pin(s) name another analysis's universe only because their file has "
            "none of that id"
        )
    if kind == "two_names":
        return f"{len(notes)} result(s) have two names"
    if kind == "unplanned":
        return f"{len(notes)} output(s) have no planned result"
    if kind == "not_built":
        return f"{len(notes)} output(s) aren't built in some universe, where a switch has no case"
    if kind == "same_computation":
        made = sum(len(note.results) for note in notes)
        return f"{len(notes)} computation(s) repeated across universes, in {made} result(s)"
    return f"{len(notes)} command(s) name a path outside their analysis (CODE_OUTSIDE_ANALYSIS)"
