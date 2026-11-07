"""§7 Inputs: an input's `path` names a file, or a stand-in for one (`MISSING_INPUT_FILE`),
tracked in the repository that holds its analysis (`INPUT_NOT_TRACKED`), inside its analysis's
folder and outside every analysis below it (`INPUT_IN_ANOTHER_ANALYSIS`); and no input's or
declaration's `path` is, or lies inside, the `results/` or `.astra/` of an analysis of the
stack (`RESERVED_PATH`, §5 *The folder*).

A path is joined to its file's folder and tidied as text, and names the entry at exactly that
path, a symlink never followed (Annex B). Each analysis is read through its own Reader, in the
working tree or at a commit. Stand-ins are those `sources.standins` registers. An input that
breaks `MISSING_INPUT_FILE` isn't checked by `INPUT_NOT_TRACKED` (Annex D case 8).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator, Sequence

from astra import model
from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.sources import paths
from astra.sources.reader import Reader
from astra.sources.standins import StandIn, registered
from astra.stack import Member

CODES = frozenset(
    {"MISSING_INPUT_FILE", "INPUT_NOT_TRACKED", "INPUT_IN_ANOTHER_ANALYSIS", "RESERVED_PATH"}
)

RESERVED = ("results", ".astra")
"""The folders of an analysis that belong to runners (§5 *The folder*)."""


def check(context: Context) -> Iterator[Diagnostic]:
    standins = registered()
    for member, analysis in context.stack.determined():
        yield from _inputs(context, member, analysis, standins)
        yield from _reserved(context, member, analysis)


def _inputs(
    context: Context, member: Member, analysis: model.Analysis, standins: Sequence[StandIn]
) -> Iterator[Diagnostic]:
    reader, folder = member.reader, member.identity.folder
    joined = {id_: paths.join(folder, input_.path) for id_, input_ in analysis.inputs.items()}
    places = {
        place
        for path in joined.values()
        if path is not None
        for place in (path, *(standin.place(path) for standin in standins))
    }
    tracked = reader.tracked(folder, places)
    for id_, input_ in analysis.inputs.items():
        path, written = joined[id_], input_.path
        at = context.at(member.identity, ("inputs", id_, "path"))
        if path is None:
            message = f"`{written}` goes above the top of the repository, so it names no file"
            yield context.diagnostic("MISSING_INPUT_FILE", message, at)
            message = f"`{written}` is outside this analysis's folder: {_ELSEWHERE}"
            yield context.diagnostic("INPUT_IN_ANOTHER_ANALYSIS", message, at)
            continue
        why = _no_file(reader, path, standins)
        if why is not None:
            yield context.diagnostic("MISSING_INPUT_FILE", f"`{written}` {why}", at)
        elif path not in tracked and not any(
            standin.place(path) in tracked and standin.recognises(reader, path)
            for standin in standins
        ):
            message = (
                f"`{written}` isn't tracked in the repository that holds this analysis: `git "
                "add` it (a file kept in a submodule is never tracked here, §7)"
            )
            yield context.diagnostic("INPUT_NOT_TRACKED", message, at)
        why = _elsewhere(reader, folder, path)
        if why is not None:
            yield context.diagnostic("INPUT_IN_ANOTHER_ANALYSIS", f"`{written}` {why}", at)


_ELSEWHERE = "another analysis's input is read by its address, such as `<declaration>.<input>`"


def _no_file(reader: Reader, path: str, standins: Sequence[StandIn]) -> str | None:
    """Why `path` names neither a file nor a stand-in for one; None where it names one."""
    entry = reader.stat(path)
    if entry is not None and entry.kind == "file":
        return None
    if entry is not None and entry.kind == "folder":
        return "is a folder: an input is one file, and data in many files is many inputs"
    if entry is not None and entry.kind == "gitlink":
        return (
            "is a submodule: data kept in another repository isn't an input, so get it "
            "through an output's recipe, or declare the analysis it belongs to"
        )
    if any(standin.recognises(reader, path) for standin in standins):
        return None
    known = ", ".join(standin.name for standin in standins)
    if entry is not None:  # a symlink
        return f"is a symlink, which is never followed (Annex B), and no stand-in of {known}"
    return f"names no file, and no stand-in of {known}"


def _elsewhere(reader: Reader, folder: str, path: str) -> str | None:
    """Why the file at `path` isn't its analysis's, whose folder is `folder`; None where it
    is inside that folder and outside every folder below it holding an `astra.yaml` file."""
    if not paths.lies_inside(path, folder):
        return f"is outside this analysis's folder: {_ELSEWHERE}"
    below = (path[len(folder) + 1 :] if folder else path).split("/")[:-1]
    for count in range(1, len(below) + 1):
        inner = posixpath.join(folder, *below[:count])
        entry = reader.stat(posixpath.join(inner, "astra.yaml"))
        if entry is not None and entry.kind == "file":
            return f"is inside `{inner}`, which holds an analysis of its own: {_ELSEWHERE}"
    return None


def _reserved(context: Context, member: Member, analysis: model.Analysis) -> Iterator[Diagnostic]:
    """`RESERVED_PATH` on each path `member`'s file writes, against the analyses read in the
    same tree as it: the working tree, or the same commit."""
    # OPEN(O15): paths read in different trees are never compared.
    reserved = [
        posixpath.join(other.identity.folder, name)
        for other in context.stack.analyses.values()
        if other.identity.commit == member.identity.commit
        for name in RESERVED
    ]
    written = [(("inputs", id_, "path"), input_.path) for id_, input_ in analysis.inputs.items()]
    for id_, declared in analysis.analyses.items():
        if declared.path is not None:
            written.append((("analyses", id_, "path"), declared.path))
    for pointer, path in written:
        tidied = paths.join(member.identity.folder, path)
        if tidied is None:
            continue
        for folder in reserved:
            if tidied == folder or paths.lies_inside(tidied, folder):
                where = "is" if tidied == folder else "lies inside"
                message = (
                    f"`{path}` {where} `{folder}`, which belongs to runners (§5): move it out "
                    "of every analysis's `results/` and `.astra/`"
                )
                at = context.at(member.identity, pointer)
                yield context.diagnostic("RESERVED_PATH", message, at)
                break
